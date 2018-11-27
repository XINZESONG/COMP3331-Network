import sys, socket, random
from stp_packet import StpPacket
import log_helper


DEBUG_MODE = False
# argv
argv_port = ''
argv_filename = ''
# statistics
num_received_bytes = 0
num_seg = 0
num_data_seg = 0
num_data_error = 0
num_dup_data_seg = 0
num_dup_ack = 0


def parse_argv():
    global DEBUG_MODE
    global argv_port
    global argv_filename

    if len(sys.argv) != 3:
        print('Usage:' +
              'python receiver.py receiver_port output_file_name')
        sys.exit(1)

    argv_port = int(sys.argv[1])
    argv_filename = sys.argv[2]


def wait_for_handshake(udp_socket):
    global DEBUG_MODE
    global argv_port
    global num_seg

    data, address = udp_socket.recvfrom(argv_port)
    log_helper.init('Receiver_log.txt')
    num_seg += 1
    packet1 = StpPacket()
    packet1.from_byte_array(data)
    log_helper.log_packet('rcv', packet1)

    client_isn = packet1.sequenceNum

    # Base on the sample log, it seems that we do need to use random server_isn
    # server_isn = random.randint(0, 2 ** 32)
    server_isn = 0
    if not(packet1.isValid and packet1.isSyn and packet1.ackNum == 0):
        print('Receiver: Connection error')
        sys.exit(1)

    # Send ACK
    packet2 = StpPacket()
    packet2.isSyn = True
    packet2.sequenceNum = server_isn
    packet2.ackNum = client_isn + 1
    udp_socket.sendto(packet2.to_byte_array(), address)
    log_helper.log_packet('snd', packet2)

    # Receive ACK
    data, _ = udp_socket.recvfrom(argv_port)
    num_seg += 1
    packet3 = StpPacket()
    packet3.from_byte_array(data)
    log_helper.log_packet('rcv', packet3)
    if not(packet3.isValid and packet3.sequenceNum == client_isn + 1 and packet3.ackNum == server_isn + 1):
        print('Receiver: Connection error')
        sys.exit(1)

    if DEBUG_MODE:
        print('Receiver: handshake success')
    return client_isn, server_isn


def receive_file(udp_socket, client_isn, server_isn):
    global DEBUG_MODE
    global argv_filename
    global argv_port
    global num_received_bytes
    global num_seg
    global num_data_seg
    global num_data_error
    global num_dup_data_seg
    global num_dup_ack

    if DEBUG_MODE:
        print('Start Receive File')

    packets_window = []
    WINDOW_SIZE = 10
    next_seq_num = 0
    with open(argv_filename, 'wb') as f:
        while True:
            try:
                data, sender_address = udp_socket.recvfrom(argv_port)
                num_seg += 1

                p = StpPacket()
                p.from_byte_array(data)
                log_helper.log_packet('rcv', p)
                if not p.isFin:
                    num_data_seg += 1
                    if not p.isValid:
                        num_data_error += 1

                if not p.isValid:
                    # Any segment that is found corrupted is discarded at
                    # the receiver without generating a duplicate Ack.
                    continue

                if p.isFin:
                    f.close()
                    tear_down(udp_socket, sender_address, p, client_isn, server_isn, next_seq_num)
                    break
                else:
                    # we do not count the segment into data segment if it is invalid

                    if next_seq_num == p.sequenceNum - client_isn - 1:
                        if DEBUG_MODE:
                            print("receiver: receive " + str(next_seq_num))
                        f.write(p.data)
                        next_seq_num += len(p.data)

                        while True:
                            next_packet = None
                            for p in packets_window:
                                if p.sequenceNum - client_isn - 1 == next_seq_num:
                                    next_packet = p
                                    break
                            if next_packet is None:
                                break
                            else:
                                packets_window.remove(next_packet)
                                f.write(next_packet.data)
                                next_seq_num += len(next_packet.data)

                        num_received_bytes = next_seq_num

                        # send ACK
                        ack_packet = StpPacket()
                        ack_packet.isAck = True
                        ack_packet.ackNum = next_seq_num + server_isn + 1
                        udp_socket.sendto(ack_packet.to_byte_array(), sender_address)
                        log_helper.log_packet('snd', ack_packet)
                    else:
                        if p.sequenceNum < next_seq_num:
                            # Duplicate data segments
                            num_dup_data_seg += 1
                        # reacknowledge
                        num_dup_ack += 1
                        ack_packet = StpPacket()
                        ack_packet.isAck = True
                        ack_packet.ackNum = next_seq_num + server_isn + 1
                        udp_socket.sendto(ack_packet.to_byte_array(), sender_address)
                        log_helper.log_packet('snd', ack_packet)

                        packets_window.append(p)
                        if len(packets_window) >= WINDOW_SIZE:
                            packets_window.pop(0)
            except socket.timeout:
                print("Receiver: Connection Timeout")
                sys.exit(0)


def tear_down(udp_socket, address, p1, client_isn, server_isn, final_seq_no):
    global argv_port
    global DEBUG_MODE
    global num_seg

    if DEBUG_MODE:
        print("Receiver: Client Tear Down Init")

    p2 = StpPacket()
    p2.isAck = True
    p2.ackNum = p1.sequenceNum - client_isn - 1 + 1 + server_isn + 1
    udp_socket.sendto(p2.to_byte_array(), address)
    log_helper.log_packet('snd', p2)

    p3 = StpPacket()
    p3.isFin = True
    p3.sequenceNum = server_isn + 1 + final_seq_no
    udp_socket.sendto(p3.to_byte_array(), address)
    log_helper.log_packet('snd', p3)

    while True:
        data, sender_address = udp_socket.recvfrom(argv_port)
        num_seg += 1
        if len(data) == 0:
            break
        p4 = StpPacket()
        p4.from_byte_array(data)
        log_helper.log_packet('rcv', p4)
        if p4.isValid:
            if p4.isAck and p4.ackNum - client_isn - 1 == p3.sequenceNum + 1 - server_isn - 1:
                break


def main():
    global argv_port

    global num_received_bytes
    global num_seg
    global num_data_seg
    global num_data_error
    global num_dup_data_seg
    global num_dup_ack

    parse_argv()

    address = ('127.0.0.1', argv_port)
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.bind(address)

    client_isn, server_isn = wait_for_handshake(udp_socket)

    receive_file(udp_socket, client_isn, server_isn)
    udp_socket.close()

    log_helper.log_text('=============================================================')
    log_helper.log_text('Amount of data received (bytes)\t' + str(num_received_bytes))
    log_helper.log_text('Total Segments Received\t' + str(num_seg))
    log_helper.log_text('Data segments received\t' + str(num_data_seg))
    log_helper.log_text('Data segments with Bit Errors\t' + str(num_data_error))
    log_helper.log_text('Duplicate data segments received\t' + str(num_dup_data_seg))
    log_helper.log_text('Duplicate ACKs sent\t' + str(num_dup_ack))
    log_helper.log_text('=============================================================')
    log_helper.close()


if __name__ == '__main__':
    main()
