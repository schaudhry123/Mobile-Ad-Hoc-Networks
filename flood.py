def flood_receive(message, message_hist):
    initiator, seq_num = message['initiator'], message['seq_num']

    if (initiator, seq_num) in message_hist:
        return

    destination = message['destination']
    if destination == my_id:
        print("Received the message!")

    devices = filter_devices_list

    # send_to_devices(devices)

def filter_devices_list(initiator, source, devices):
    forward_devices = []

    for device in devices:
        if device[0] != initiator and device[0] != source:
            forward_devices.append(device)