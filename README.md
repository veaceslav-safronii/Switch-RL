1 2 3

Safronii Veaceslav - 334CD
# Switch Implementation

## Description of the Solution

This project implements the functionality of an Ethernet switch with VLAN and STP. The implementation is done in Python and uses the `wrapper` library for interaction with the data link layer.

### Switching Process

1. **Updating the MAC Table**:
   - When a frame is received, the source MAC address and the interface are stored in the MAC table.

2. **Forwarding Frames**:
   - The switch checks if the destination MAC address is in the MAC table and it is unicast. If it is, the frame is sent to the corresponding port. If not, the frame is broadcast to all ports except the incoming port.

### VLAN

1. **Parsing config file**
   - The function `parse_config(config_file)` parses througth the config and saves the switch priority, the vlan ids of the access ports and trunk ports.

2. **Handling VLAN Frames**:
   - The function `vlan_handler(src_interface, dest_interface, data, length, vlan_id)` handles VLAN frames and forwards them to the necessary ports.
   - It adds or removes the VLAN tag based on the type of the source and destination ports:
   1. If the destination port is a trunk port and the source port is an access port, the VLAN tag is added to the frame.
   2. If the destination port is an access port and the source port is a trunk port, the VLAN tag is removed from the frame.
   - The function ensures that frames are only forwarded to ports with the matching VLAN ID or to trunk ports.

### STP (Spanning Tree Protocol)

1. **Sending BPDU Frames**:
- The function `send_stp_bpdu(interface)` creates and sends a bpdu frame with necessary headers and fields like root_bridge_id, root_path_cost and bridge_id et al.

2. **Receiving BPDU Frames**:
- The function `recv_stp_bpdu(data)` receives and parses a BPDU frame. It extracts the root bridge id, the path cost to the root bridge and the bridge id of the sender.

3. **Initial Port States**:
   - All trunk ports are initially set to the "BLOCKING" state to prevent loops.
   - All access ports are set to the "DESIGNATED" state.

4. **Handling BPDU Frames**:

   If the destination MAC address matches the BPDU address, the switch processes the BPDU frame.

   The switch compares the root bridge id in the received BPDU frame with its own.
   
   1. If the received BPDU frame has a root bridge id smaller than the curent one, the switch updates its root bridge id, root path cost and sets as the root port the interface the bpdu was received at.

   2. If the switch was root, it blocks the trunk ports and sets the root port to listen.

   3. If the sender of BPDU has the same root bridge, the switch updates the path cost and port states if necessary.

   4. If the sender has the same bridge ID as the switch's own bridge ID, the port is set to "BLOCKING".

   5. If the switch is the root bridge, it sets all ports to "DESIGNATED" and resets the root path cost and root port.

   In VLAN handler is added a verification of the destination interface state, if it is blocked it won't send the data to that interface.