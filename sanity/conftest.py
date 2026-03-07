def pytest_addoption(parser):
    parser.addoption(
        "--dut-ip", action="store", required=True, help="DUT IP address"
    )
    parser.addoption(
        "--dut-user", action="store", required=True, help="DUT SSH username"
    )
    parser.addoption(
        "--dut-pass", action="store", required=True, help="DUT SSH password"
    )
