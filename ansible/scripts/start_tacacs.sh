#!/bin/sh

# Start the daemon in background, redirect all I/O, and ensure script exits
nohup /root/tacacs_daily_daemon < /dev/null > /dev/null 2>&1 &
sleep 0.5
exit 0
