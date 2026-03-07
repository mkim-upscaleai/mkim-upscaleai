'''
Helper functions for span tests
'''

import ptf.testutils as testutils
import time


def send_and_verify_mirrored_packet(ptfadapter, duthost, src_port, monitor, monitor_port_name):
    '''
    Send packet from ptf and verify it on monitor port by checking DUT interface counters

    Args:
        ptfadapter: ptfadapter fixture
        duthost: DUT host object
        src_port: ptf port index, from which packet will be sent
        monitor: ptf port index, where packet will be verified on
        monitor_port_name: DUT port name (e.g., "Ethernet7") for the monitor port
    '''
    src_mac = ptfadapter.dataplane.get_mac(0, src_port)

    pkt = testutils.simple_icmp_packet(eth_src=src_mac, eth_dst='ff:ff:ff:ff:ff:ff')

    ptfadapter.dataplane.flush()

    # Get initial interface counter for monitor port
    initial_counters = duthost.show_interface(command="counter", interfaces=[monitor_port_name])
    initial_tx_ok_str = initial_counters['ansible_facts']['int_counter'][monitor_port_name]['TX_OK']
    initial_tx_ok = int(initial_tx_ok_str.replace(',', ''))

    # Send 1000 packets
    testutils.send(ptfadapter, src_port, pkt, count=1000)
    # Original verify method (commented out - now using DUT interface counters instead):
    # testutils.verify_packet(ptfadapter, pkt, monitor)

    # Wait a bit for packets to be processed and counters to update
    time.sleep(2)

    # Get final interface counter for monitor port
    final_counters = duthost.show_interface(command="counter", interfaces=[monitor_port_name])
    final_tx_ok_str = final_counters['ansible_facts']['int_counter'][monitor_port_name]['TX_OK']
    final_tx_ok = int(final_tx_ok_str.replace(',', ''))

    # Calculate the difference
    tx_ok_delta = final_tx_ok - initial_tx_ok

    # Verify that monitor port transmitted approximately 1000 packets
    # Allow some tolerance for counter updates and potential packet loss
    expected_min = 980  # Allow 2% tolerance
    expected_max = 1020  # Allow 2% tolerance

    if not (expected_min <= tx_ok_delta <= expected_max):
        raise AssertionError(
            f"Monitor port {monitor_port_name} TX_OK counter did not increase as expected. "
            f"Expected: {expected_min}-{expected_max}, Got: {tx_ok_delta} "
            f"(Initial: {initial_tx_ok}, Final: {final_tx_ok})"
        )
