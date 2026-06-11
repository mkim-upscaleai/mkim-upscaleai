import time
import re
from .base_console_conn import BaseConsoleConn
try:
    from netmiko.ssh_exception import NetMikoAuthenticationException
except ImportError:
    from netmiko.exceptions import NetMikoAuthenticationException


class TelnetConsoleConn(BaseConsoleConn):
    def __init__(self, **kwargs):
        # For telnet console, neither console username or password is needed
        # so we assign sonic_username/sonic_password to username/password
        kwargs['host'] = kwargs['console_host']
        kwargs['port'] = kwargs['console_port']
        # Don't set the value of password here because we will loop
        # among all passwords in __init__
        kwargs['username'] = kwargs['sonic_username']
        kwargs['console_username'] = kwargs['sonic_username']
        kwargs['console_password'] = kwargs['sonic_password']
        kwargs['device_type'] = "_telnet"
        super(TelnetConsoleConn, self).__init__(**kwargs)

    # Matches ANSI/VT100 CSI sequences and single-char C1 codes (e.g. \x1bE NEL).
    _ANSI_ESCAPE = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def read_channel(self):
        """Strip ANSI/VT100 escape sequences from raw channel output.

        The console terminal server injects \x1bE (NEL) mid-word when a command
        echo wraps at column 80, which breaks netmiko's command_echo_read pattern
        match and causes ReadTimeout. Stripping here keeps the byte stream clean.
        """
        output = super(TelnetConsoleConn, self).read_channel()
        return self._ANSI_ESCAPE.sub('', output)

    def session_preparation(self):
        super(TelnetConsoleConn, self).session_preparation()
        # SONiC uses KLISH (sonic-cli) as the console login shell, which does not
        # support Linux shell commands. Detect it by the absence of "user@host" in
        # base_prompt (netmiko strips the trailing '#'/'$', so don't check for it).
        clean_prompt = self._ANSI_ESCAPE.sub('', self.base_prompt).strip()
        if '@' not in clean_prompt:
            # KLISH detected — drop to bash so send_command works normally.
            self.write_channel("bash" + self.RETURN)
            self.read_until_pattern(pattern=r"@[^@\n]*[$#]",
                                    re_flags=re.MULTILINE, read_timeout=15)
            self.set_base_prompt()

        # Set a wide terminal column count to prevent TTY-level line wrapping.
        self.write_channel("stty cols 200" + self.RETURN)
        self.read_until_pattern(pattern=r"[$#]", read_timeout=10)

    def telnet_login(
        self,
        pri_prompt_terminator=r".*# ",
        alt_prompt_terminator=r".*\$ ",
        # NOTE: patterns require a trailing colon so that stale terminal-server
        # output like "Login incorrect" (no colon) does not falsely match the
        # username prompt and cause us to send the username in response to a
        # "Password:" prompt that is actually still on the line from a prior
        # failed session.
        username_pattern=r"(?:user:|username:|login:|user name:)",
        pwd_pattern=r"assword:",
        delay_factor=1,
        max_loops=60,
    ):
        """Telnet login. Can be username/password or just password."""
        # Netmiko's select_delay_factor() collapses delay_factor to ~0.1 when
        # fast_cli=True (which BaseConsoleConn sets). Upstream's 20-loop default
        # was tuned for delay_factor=1 (~20 s of patience); with 0.1 that shrinks
        # to ~1-2 s, which is not enough for console login over a terminal server
        # where the DUT may replay a buffered banner, run PAM, and render a
        # multi-line motd before printing the shell prompt. Floor the delay so
        # our 60-loop budget yields ~30 s of real patience regardless of fast_cli.
        delay_factor = max(self.select_delay_factor(delay_factor), 0.5)
        time.sleep(1 * delay_factor)

        output = ""
        return_msg = ""
        login_failure_prompt = r".*incorrect"
        username_sent = False
        password_sent = False
        i = 1
        while i <= max_loops:
            try:
                output = self.read_channel()
                return_msg += output

                # Search for username pattern / send username
                if not username_sent and re.search(username_pattern, output, flags=re.I):
                    self.write_channel(self.username + self.TELNET_RETURN)
                    username_sent = True
                    time.sleep(1 * delay_factor)
                    output = self.read_channel()
                    return_msg = output

                # Search for password pattern / send password
                if username_sent and not password_sent and re.search(pwd_pattern, output, flags=re.I):
                    self.write_channel(self.password + self.TELNET_RETURN)
                    time.sleep(0.5 * delay_factor)
                    password_sent = True
                    output = self.read_channel()
                    return_msg += output
                    if re.search(
                        pri_prompt_terminator, output, flags=re.M
                    ) or re.search(alt_prompt_terminator, output, flags=re.M):
                        return return_msg

                # Support direct telnet through terminal server
                if re.search(r"initial configuration dialog\? \[yes/no\]: ", output):
                    self.write_channel("no" + self.TELNET_RETURN)
                    time.sleep(0.5 * delay_factor)
                    count = 0
                    while count < 15:
                        output = self.read_channel()
                        return_msg += output
                        if re.search(r"ress RETURN to get started", output):
                            output = ""
                            break
                        time.sleep(2 * delay_factor)
                        count += 1

                # Check for device with no password configured
                if re.search(r"assword required, but none set", output):
                    self.remote_conn.close()
                    msg = "Login failed - Password required, but none set: {}".format(
                        self.host
                    )
                    raise NetMikoAuthenticationException(msg)

                # Check if proper data received
                if re.search(pri_prompt_terminator, output, flags=re.M) or re.search(
                    alt_prompt_terminator, return_msg, flags=re.M
                ):
                    return return_msg

                #  Check if login failed - only after password has been sent to
                #  avoid false positives from stale "Login incorrect" output
                #  left on the console from a previous failed session
                if password_sent and re.search(login_failure_prompt, output, flags=re.M):
                    self.remote_conn.close()
                    # Wait a short time or the next login will be refused
                    time.sleep(1 * delay_factor)
                    msg = "Login failed: {} password: {}".format(self.host, self.password)
                    raise NetMikoAuthenticationException(msg)

                self.write_channel(self.TELNET_RETURN)
                time.sleep(0.5 * delay_factor)
                i += 1
            except EOFError:
                self.remote_conn.close()
                msg = "Login failed: {}".format(self.host)
                raise NetMikoAuthenticationException(msg)

        # Last try to see if we already logged in
        self.write_channel(self.TELNET_RETURN)
        time.sleep(0.5 * delay_factor)
        output = self.read_channel()
        return_msg += output
        if re.search(pri_prompt_terminator, output, flags=re.M) or re.search(
            alt_prompt_terminator, output, flags=re.M
        ):
            return return_msg

        self.remote_conn.close()
        msg = "Login failed: {}".format(self.host)
        raise NetMikoAuthenticationException(msg)
