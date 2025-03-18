#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    #dest_mac, src_mac, ethertype = struct.unpack('!6s6sH', data[:14])
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def send_bdpu_every_sec():
    while True:
        if is_root:
            for i in interfaces:
                if is_trunk_port(i):
                    send_stp_bpdu(i)
        time.sleep(1)

def is_unicast(mac):
    return int(mac.split(":")[0], 16) & 1 == 0

def is_trunk_port(interface):
    return get_interface_name(interface) in trunk_ports

# Reading configuration of switches
def parse_config(config_file):
    vlan_ids = {}
    trunk_ports = []
    with open(config_file, "r") as f:
        lines = f.readlines()
        priority = int(lines[0].strip())

        for line in lines[1:]:
            line = line.strip().split()
            interface = line[0]
            if line[1] == "T":
                trunk_ports.append(interface)
            else:
                vlan_ids[interface] = int(line[1])
    return priority, vlan_ids, trunk_ports

# Manages VLAN Headers and forwards the frame accordingly
def vlan_handler(src_interface, dest_interface, data, length,
                vlan_id):
    # Get the interface name
    dest_interface_name = get_interface_name(dest_interface)
    # Drops the frame if the port is BLOCKING
    if (ports[dest_interface] == "BLOCKING"):
        return

    # Check if the destination interface is a trunk port
    if is_trunk_port(dest_interface):
        # Check if the source interface is an access port to add the VLAN tag
        if is_trunk_port(src_interface) == 0:
            tagged_frame = data[0:12] + create_vlan_tag(vlan_id) + data[12:]
            length += 4
            send_to_link(dest_interface, length, tagged_frame)
        else:
            send_to_link(dest_interface, length, data)
    else:
        # Check if the vlan ids match
        if vlan_ids[dest_interface_name] == vlan_id:
            # Check if the source interface is a trunk port to remove the VLAN tag
            if is_trunk_port(src_interface):
                    data = data[0:12] + data[16:]
                    length -= 4
                    send_to_link(dest_interface, length, data)
            else:
                send_to_link(dest_interface, length, data)

# Create a BPDU frame and send it to the interface
def send_stp_bpdu(interface):
    protocol_id = 0x0000
    protocol_version = 0x00
    bpdu_type = 0x00
    flags = 0x00
    port_id = 0x8000
    message_age = 0x0000
    max_age = 0x0000
    hello_time = 0x0000
    forward_delay = 0x0000
    # BPDU header packing
    bpdu = struct.pack('!HBBBQIQHHHHH',protocol_id, protocol_version,
                        bpdu_type, flags, root_bridge_id, root_path_cost,
                        own_bridge_id, port_id,  message_age, max_age,
                        hello_time, forward_delay)
    # LLC header
    llc = struct.pack('!BBB', 0x42, 0x42, 0x03)
    llc_length = len(llc) + len(bpdu)
    # Converts the BPDU mac address to bytes
    dest_mac = bytes.fromhex(bpdu_addr.replace(":", ""))

    frame = struct.pack('!6s6sH', dest_mac,
                        get_switch_mac(), llc_length) + llc + bpdu
    length = len(frame)

    send_to_link(interface, length, frame)

# Extracts the necessary information from the BPDU frame
def recv_stp_bpdu(data):
    ethernet_header = struct.unpack('!6s6sH', data[:14])
    llc_header = struct.unpack('!BBB', data[14:17])
    bpdu = struct.unpack('!HBBBQIQHHHHH', data[17:])
    sender_root_bridge_id, sender_path_cost, bridge_id = bpdu[4], bpdu[5], bpdu[6]

    return sender_root_bridge_id, bridge_id, sender_path_cost

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    switch_id = sys.argv[1]

    global interfaces

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    global priority, vlan_ids, trunk_ports
    file =  './configs/switch' + switch_id + '.cfg'
    priority, vlan_ids, trunk_ports = parse_config(file)
    
    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    global own_bridge_id, root_bridge_id, root_path_cost
    own_bridge_id = priority
    root_bridge_id = own_bridge_id
    root_path_cost = 0
    root_port = None

    global is_root
    is_root = True

    global bpdu_addr
    bpdu_addr = "01:80:c2:00:00:00"

    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    # Printing interface names
    for i in interfaces:
        print(get_interface_name(i))

    mac_table = {}
    global ports
    ports = {}

    for i in interfaces:
        if is_trunk_port(i):
            ports[i] = "BLOCKING"
        else:
            ports[i] = "DESIGNATED"

    while True:
        # Note that data is of type bytes([...]).
        # b1 = bytes([72, 101, 108, 108, 111])  # "Hello"
        # b2 = bytes([32, 87, 111, 114, 108, 100])  # " World"
        # b3 = b1[0:2] + b[3:4].
        interface, data, length = recv_from_any_link()

        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)

        # Note. Adding a VLAN tag can be as easy as
        # tagged_frame = data[0:12] + create_vlan_tag(10) + data[12:]

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')

        mac_table[src_mac] = interface

        # Sets the vlan_id if the interface is an access port
        if is_trunk_port(interface) == 0:
            vlan_id = int(vlan_ids[get_interface_name(interface)])
        # Checks if the destination MAC is a unicast MAC
        if is_unicast(dest_mac):
            if dest_mac in mac_table:
                vlan_handler(interface, mac_table[dest_mac], data, length,
                            vlan_id)
            else:
                for i in interfaces:
                    if i != interface:
                        vlan_handler(interface, i, data, length,
                                    vlan_id)
        else:
            if (dest_mac != bpdu_addr):
                for i in interfaces:
                    if i != interface:
                        vlan_handler(interface, i, data, length,
                                    vlan_id)
            else:
                bpdu_root_bridge_id, bpdu_bridge_id, bpdu_path_cost = recv_stp_bpdu(data)
                # Checks if the sender has a lower root bridge id
                if bpdu_root_bridge_id < root_bridge_id:
                    root_bridge_id = bpdu_root_bridge_id
                    root_path_cost = bpdu_path_cost + 10
                    root_port = interface

                    if is_root:
                        for port in ports:
                            if is_trunk_port(port):
                                ports[port] = "BLOCKING"
                        is_root = False
                        ports[root_port] = "DESIGNATED"
                    # Sends BPDU to all trunk ports except the root port
                    for i in interfaces:
                        if is_trunk_port(i) and i != root_port:
                            send_stp_bpdu(i)

                elif bpdu_root_bridge_id == root_bridge_id:
                    if interface == root_port and bpdu_path_cost + 10 < root_path_cost:
                        root_path_cost = bpdu_path_cost + 10

                    elif interface != root_port:
                        if bpdu_path_cost > root_path_cost:
                            if ports[interface] != "DESIGNATED":
                                ports[interface] = "DESIGNATED"
                
                elif bpdu_bridge_id == own_bridge_id:
                    ports[interface] = "BLOCKING"
                
                if own_bridge_id == root_bridge_id:
                    for port in ports:
                        ports[port] = "DESIGNATED"
                    root_path_cost = 0
                    root_port = None
                    is_root = True
                else:
                    is_root = False
        # data is of type bytes.
        # send_to_link(i, length, data)

if __name__ == "__main__":
    main()
