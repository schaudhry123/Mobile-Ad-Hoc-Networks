import sys
from threading import Thread
import socket
import bluetooth
import time
import signal
import pickle

# List of all devices in the network
devices = []

# Current process id
my_id = ''

# Sequence number of the process
seq_num = 0

# Message history - list of tuples (initiator, seq_num)
message_hist = []

# Server socket to close on signal handler
s = None

def main(argv):
    ''' Start up the server and client thread and keep the program running '''

    global my_id
    my_id = argv[1]
    host, port = get_devices_info(argv[0])
    algorithm = argv[2].lower()

    try:
        server_thread = Thread(target=setup_server, args=(host, port, algorithm))
        server_thread.daemon = True
        server_thread.start()
    except:
        print("Failed to start server, exiting.")
        sys.exit(0)

    try:
        client_thread = Thread(target=setup_client, args=(algorithm, ))
        client_thread.daemon = True
        client_thread.start()
    except:
        print("Failed to start client, exiting.")
        sys.exit(0)

    while True:
        time.sleep(100)


def setup_client(algorithm):
    ''' Reads in and handles input from the user '''

    global seq_num
    while True:
        user_input = raw_input()

        if user_input == 'exit':
            break

        if user_input:
            command = user_input.split()

            if command[0] == 'send':
                destination = int(user_input[5:])
                seq_num += 1

                if(algorithm == 'flooding'):
                    message = {
                        'source'        : my_id,
                        'destination'   : destination,
                        'initiator'     : my_id,
                        'seq_num'       : seq_num
                    }
                    flood_send(message, devices)
                elif(algorithm == 'dsr'):
                    message = {
                        'path': [my_id],
                        'destination': destination,
                        'seq_num': seq_num,
                        'initiator': my_id
                    }
                    flood_send(message, devices)

            elif command[0] == 'add' and command[1] == 'connection':
                user_input = raw_input('Enter the device information `<id> <host> <port>`: ').split()
                add_device(user_input)

            elif command[0] == 'break' and command[1] == 'connection':
                user_input = raw_input('Enter which connection to break: ')
                break_connection(user_input)

            elif command[0] == 'display':
                display_devices()

def display_devices():
    for device in devices:
        print device

def add_device(user_input):
    ''' Add a device to the devices list '''

    device = {
        'id'    : user_input[0],
        'host'  : user_input[1],
        'port'  : user_input[2]
    }
    devices.append(device)

def break_connection(device_id):
    idx = -1
    for i, device in enumerate(devices):
        if device['id'] == device_id:
            idx = i

    if idx == -1:
        print("Device {0} does not exist!")
        return

    del devices[idx]
    print("Connection successfully broken.")


def flood_send(message, device_list):
    ''' Send a message out to all nearby neighbors '''
    message_hist.append((message['initiator'], message['seq_num']))
    print("Flood sending to {0}".format(device_list))
    for device in device_list:
        send_message(message, device)

def send_message(message, device):
    ''' Connect to the destination device and send a message to it, closing
        the socket after the message is sent '''

    # print("device = {0}".format(device))

    try:
        s = create_connection(device)

        if not s:
            print("Error: Could not connect to device.")
            return

        serialized_message = pickle.dumps(message, -1)
        s.send(serialized_message)
        s.close()

    except Exception as e:
        print("Unable to connect to device " + str(device['id']) + ": {0}".format(e))

def create_connection(device):
    ''' Create a connection to the device and return the socket connection '''

    host = device['host']
    port = int(device['port'])
    try:
        s = bluetooth.BluetoothSocket( bluetooth.RFCOMM )
        s.connect((host, port))
        return s
    except Exception as e:
        print("Error connecting to device: {0}".format(e))

    return None

def get_device_by_id(id):
    # print("Getting device " + str(id))
    for device in devices:
        # print("Comparing {0} and {1}".format(device['id'], id))
        if device['id'] == id:
            # print("Found!")
            return device
    # print("nah!")
    return None

def setup_server(host, port, algorithm):
    ''' Create the server and begin waiting for new connections '''

    connections = []

    global s
    s = bluetooth.BluetoothSocket( bluetooth.RFCOMM )
    s.bind(("", port))
    s.listen(5)

    while True:
        conn, addr = s.accept()
        connections.append(conn)
        conn_thread = Thread(target = readMessagesFromConnection, args = (conn, algorithm, ))
        conn_thread.start()

    for conn in connections:
        conn.close()
    s.close()

def readMessagesFromConnection(conn, algorithm):
    ''' Keep reading messages from the established connection until it is closed '''

    while True:
        try:
            data = conn.recv(512)
        except Exception as e:
            break

        if not data:
            break

        message = pickle.loads(data)
        if('type' in message):
            dsr_request_reply(message)
        else:
            destination = message['destination']
            message_id = (message['initiator'], message['seq_num'])

            if destination == int(my_id):
                print("Reached the final destination!")
                if(algorithm == 'dsr'):
                    #Send a Route Request Reply
                    path = message['path']
                    path.append(my_id)
                    index = len(path) - 1

                    # print("path = {0} and index = {1}".format(path, index))

                    message = {
                        'type': 'rrep',
                        'index': index - 1,
                        'path': path
                    }
                    send_message(message, get_device_by_id(path[message['index']]))
                    # print("Finished sending message")
            elif message_id not in message_hist:
                if(algorithm == 'flooding'):
                    flood_receive(message)
                elif(algorithm == 'dsr'):
                    dsr_receive(message)

def dsr_request_reply(message):
    # print("Received a dsr request reply = {0}".format(message))
    if(message['index'] == 0):
        print('Received Route Request Reply along path: ' +  str(message['path']))
        return

    path = message['path']
    message = {
        'type': 'rrep',
        'index': message['index'] - 1,
        'path': path
    }
    send_message(message, get_device_by_id(path[message['index']]))

def flood_receive(message):
    ''' Recipient of a flood message that will forward it on to the correct neighbors '''
    source      = message['source']
    destination = message['destination']
    initiator   = message['initiator']
    seq_num     = message['seq_num']

    print("Forwarding a message that was intended for {0} from {1}".format(destination, source))
    device_list = filter_devices(source, initiator)

    message = {
        'source'        : my_id,
        'destination'   : destination,
        'initiator'     : initiator,
        'seq_num'       : seq_num
    }
    flood_send(message, device_list)

def dsr_receive(message):
    path = message['path']
    destination = message['destination']
    initiator   = message['initiator']
    seq_num     = message['seq_num']

    print("Forwarding a message that was intended for {0} from {1}".format(destination, path[-1]))
    device_list = filter_devices(path[-1], initiator)

    path.append(my_id)
    message = {
        'path': path,
        'destination'   : destination,
        'initiator'     : initiator,
        'seq_num'       : seq_num
    }
    flood_send(message, device_list)

def filter_devices(source, initiator):
    ''' Filter the list of devices such that it does not re-send to the source and initiator '''

    device_list = []
    for device in devices:
        if device['id'] != source and device['id'] != initiator:
            device_list.append(device)
    return device_list

def get_devices_info(config_file):
    ''' Parse the config file to get all devices information '''

    global devices, my_id
    cur_device = None
    with open(config_file) as f:
        for i, line in enumerate(f):
            device_info = line.split()
            device = {
                'id'    : device_info[0],
                'host'  : device_info[1],
                'port'  : device_info[2]
            }

            if my_id == device_info[0]:
                cur_device = device_info
            else:
                devices.append(device)

    return (cur_device[1], int(cur_device[2]))


def handler(signum, frame):
    s.close()
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, handler)

    if len(sys.argv) < 4:
        print("python {0} <config_file> <#> <algorithm>".format(sys.argv[0]))
    else:
        main(sys.argv[1:])