import sys, socket, random, math, time, os
from stp_packet import StpPacket
import pld
import log_helper

DEBUG_MODE = False

# Argv
argv_host_ip = ''
argv_port = ''
argv_file_name = ''
argv_mws = 50000  # Maximum window size
argv_mss = 5000  # Maximum segment size
argv_gamma = 9
# Argv for PLD
argv_pDrop = 0.5
argv_pDuplicate = 0.5
argv_pCorrupt = 0.5
argv_pOrder = 0.5
argv_maxOrder = 6
argv_pDelay = 0.5
argv_maxDelay = 10  # ms
argv_seed = 1000

# RTT
estimatedRTT = 0.5
devRTT = 0.25
timeoutInterval = estimatedRTT + argv_gamma * devRTT

# Statistics
num_transmitted = 0
num_retrans_timeout = 0
num_retrans_fast = 0
num_dup_ack = 0


def update_timeout(sampleRTT):
    global estimatedRTT
    global devRTT
    global timeoutInterval
    global argv_gamma

    alpha = 0.125
    belta = 0.25

    estimatedRTT = (1 - alpha) * estimatedRTT + alpha * sampleRTT
    devRTT = (1 - belta) * devRTT + belta * math.fabs(sampleRTT - estimatedRTT)
    timeoutInterval = estimatedRTT + argv_gamma * devRTT
    if DEBUG_MODE:
        print('sender: timeoutInterval ' + str(timeoutInterval))


def parse_argv():
    global DEBUG_MODE
    global argv_host_ip
    global argv_port
    global argv_file_name
    global argv_mws
    global argv_mss
    global argv_gamma
    global argv_pDrop
    global argv_pDuplicate
    global argv_pCorrupt
    global argv_pOrder
    global argv_maxOrder
    global argv_pDelay
    global argv_maxDelay
    global argv_seed


    if len(sys.argv) != 15:
        print('Usage:\n' +
              'python sender.py receiver_host_ip receiver_port input_file_name MWS MSS' +
              ' gamma pDrop pDuplicate pCorrupt pOrder maxOrder pDelay maxDelay seed')
        sys.exit(1)

    argv_host_ip = sys.argv[1]
    argv_port = int(sys.argv[2])
    argv_file_name = sys.argv[3]
    argv_mws = int(sys.argv[4])
    argv_mss = int(sys.argv[5])
    argv_gamma = float(sys.argv[6])
    argv_pDrop = float(sys.argv[7])
    argv_pDuplicate = float(sys.argv[8])
    argv_pCorrupt = float(sys.argv[9])
    argv_pOrder = float(sys.argv[10])
    argv_maxOrder = int(sys.argv[11])
    argv_pDelay = float(sys.argv[12])
    argv_maxDelay = int(sys.argv[13])
    argv_seed = int(sys.argv[14])


def handle_handshake(udp_socket):
    global DEBUG_MODE
    global argv_host_ip
    global argv_port
    global num_transmitted
    address = (argv_host_ip, argv_port)

    # Send First SYNC Packet
    packet1 = StpPacket()
    packet1.isSyn = True

    # Base on the sample log, it seems that we do need to use random client_isn
    # client_isn = random.randint(0, 2 ** 32)
    client_isn = 0

    packet1.sequenceNum = client_isn
    udp_socket.sendto(packet1.to_byte_array(), address)
    num_transmitted += 1

    log_helper.log_packet('snd', packet1)

    # Wait For ACK
    try:
        packet2_bytes, _ = udp_socket.recvfrom(argv_port)
        packet2 = StpPacket()
        packet2.from_byte_array(packet2_bytes)

        if not(packet2.isValid and packet2.isSyn and packet2.ackNum == client_isn + 1):
            print('Sender: Connection Error')
            sys.exit(1)

        log_helper.log_packet('rcv', packet2)
    except socket.timeout:
        print('Sender: Connection Timeout')
        sys.exit(1)

    server_isn = packet2.sequenceNum
    # Send ACK
    packet3 = StpPacket()
    packet3.sequenceNum = client_isn + 1
    packet3.ackNum = server_isn + 1
    udp_socket.sendto(packet3.to_byte_array(), address)
    num_transmitted += 1
    # We do not carry data in the third stage of the handshake
    log_helper.log_packet('snd', packet3)

    if DEBUG_MODE:
        print('Sender: handshake success')
    return client_isn, server_isn


def send_file(udp_socket, client_isn, server_isn):
    global argv_file_name
    global argv_mws
    global argv_mss
    global argv_host_ip
    global argv_port
    global DEBUG_MODE
    global timeoutInterval
    global num_transmitted
    global num_retrans_timeout
    global num_retrans_fast
    global num_dup_ack

    address = (argv_host_ip, argv_port)

    packets_window = []
    current_windows_size = 0
    read_all = False

    final_seq_no = 0

    duplicate_ack_count = 0

    start_time = 0
    measured_packet = None

    with open(argv_file_name, 'rb') as f:
        while True:
            current_segment_size = argv_mws - current_windows_size
            current_segment_size = min(current_segment_size, argv_mss)

            # Send Packet Until windows is full
            while (not read_all) and current_segment_size > 0:
                seq_no = f.tell()
                segment_data = f.read(current_segment_size)
                if len(segment_data) == 0:
                    read_all = True
                    final_seq_no = seq_no
                    break

                p = StpPacket()
                p.sequenceNum = seq_no + client_isn + 1
                p.data = segment_data

                if measured_packet is None:
                    measured_packet = p
                    start_time = time.time()

                pld.send_packet(udp_socket, p, address)
                num_transmitted += 1
                current_windows_size += current_segment_size
                packets_window.append(p)

                current_segment_size = argv_mws - current_windows_size
                current_segment_size = min(current_segment_size, argv_mss)

            if len(packets_window) == 0 and read_all:
                # All of the file have been sent successfully
                break

            # Receive Ack
            try:
                ack_packet_bytes, _ = udp_socket.recvfrom(argv_port)
                ack_packet = StpPacket()
                ack_packet.from_byte_array(ack_packet_bytes)



                if ack_packet.isValid and ack_packet.isAck:
                    log_helper.log_packet('rcv', ack_packet)
                    # If the received packet is not Ack, ignore

                    success_packets = []
                    for p in packets_window:
                        if(p.sequenceNum - client_isn - 1) + len(p.data) <= (ack_packet.ackNum - server_isn - 1):
                            success_packets.append(p)

                    if len(success_packets) > 0:
                        duplicate_ack_count = 0
                        for p in success_packets:
                            if measured_packet == p:
                                end_time = time.time()
                                update_timeout(end_time - start_time)
                                udp_socket.settimeout(timeoutInterval)
                                measured_packet = None

                            packets_window.remove(p)
                            current_windows_size -= len(p.data)

                    else:
                        # handle duplicate ack
                        duplicate_ack_count += 1
                        num_dup_ack += 1
                        log_helper.log_packet('rcv/DA', ack_packet)

                        if duplicate_ack_count == 3 and len(packets_window) > 0:
                            # fast retransmit
                            # TODO special handle for RXT log
                            log_helper.log_packet('snd/RXT', packets_window[0])
                            pld.send_packet(udp_socket, packets_window[0], address)
                            num_retrans_fast += 1
                            num_transmitted += 1
                            # Sender will not measure the sampleRTT (for maintaining its timer for timeout) for any
                            # segment that it re-transmits.
                            # measured_packet = None
                            measured_packet = packets_window[0]
                            start_time = time.time()
                else:
                    log_helper.log_packet('rcv', ack_packet)

            except socket.timeout:
                # only resent the first packet (with the smallest sequence number)
                if len(packets_window) > 0:
                    log_helper.log_packet('RXT', packets_window[0])
                    pld.send_packet(udp_socket, packets_window[0], address)
                    num_retrans_timeout += 1
                    num_transmitted += 1
                    # Sender will not measure the sampleRTT (for maintaining its timer for timeout) for any segment
                    #  that it re-transmits.
                    # measured_packet = None
                    measured_packet = packets_window[0]
                    start_time = time.time()

    if DEBUG_MODE:
        print("Sender: Send File Finish")
    return final_seq_no


def tear_down(udp_socket, client_isn, server_isn, final_seq_no):
    global DEBUG_MODE
    global argv_host_ip
    global argv_port
    global num_transmitted

    if DEBUG_MODE:
        print("Sender: Start tear_down")

    address = (argv_host_ip, argv_port)

    p1 = StpPacket()
    p1.isFin = True
    p1.sequenceNum = client_isn + 1 + final_seq_no

    udp_socket.sendto(p1.to_byte_array(), address)
    num_transmitted += 1
    log_helper.log_packet('snd', p1)

    has_ack = False
    has_fin = False
    udp_socket.settimeout(None)
    while True:
        try:
            p2_bytes, _ = udp_socket.recvfrom(argv_port)
            p2 = StpPacket()
            p2.from_byte_array(p2_bytes)

            log_helper.log_packet('rcv', p2)

            if not p2.isValid:
                continue

            if p2.isAck and (p2.ackNum - server_isn - 1) == (p1.sequenceNum - client_isn - 1 + 1) and len(p2.data) == 0:
                has_ack = True
            elif p2.isFin:
                has_fin = True
                p4 = StpPacket()
                p4.isAck = True
                p4.ackNum = p2.sequenceNum - server_isn - 1 + client_isn + 1 + 1
                udp_socket.sendto(p4.to_byte_array(), address)
                num_transmitted += 1
                log_helper.log_packet('snd', p4)

            if has_ack and has_fin:
                break

        except socket.timeout:
            print("Sender: Connection timeout")
            sys.exit(1)

    p3 = StpPacket()
    p3.isAck = True
    p3.sequenceNum = 0
    p3.ackNum = 0
    udp_socket.sendto(p3.to_byte_array(), address)
    num_transmitted += 1
    log_helper.log_packet('snd', p3)

    udp_socket.close()


def main():
    global argv_host_ip
    global argv_port
    global timeoutInterval
    global argv_file_name

    parse_argv()
    pld.config(argv_pDrop, argv_pDuplicate, argv_pCorrupt, argv_pOrder, argv_maxOrder, argv_pDelay, argv_maxDelay, argv_seed)
    log_helper.init('Sender_log.txt')

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(timeoutInterval)

    client_isn, server_isn = handle_handshake(udp_socket)

    final_seq_no = send_file(udp_socket, client_isn, server_isn)

    tear_down(udp_socket, client_isn, server_isn, final_seq_no)
    log_helper.log_text('=============================================================')
    log_helper.log_text('Size of the file (in Bytes)\t' + str(os.path.getsize(argv_file_name)))
    log_helper.log_text('Segments transmitted (including drop & RXT)\t' + str(num_transmitted))
    log_helper.log_text('Number of Segments handled by PLD\t' + str(pld.num_pld))
    log_helper.log_text('Number of Segments dropped\t' + str(pld.num_dropped))
    log_helper.log_text('Number of Segments Corrupted\t' + str(pld.num_corrupted))
    log_helper.log_text('Number of Segments Re-ordered\t' + str(pld.num_reorder))
    log_helper.log_text('Number of Segments Duplicated\t' + str(pld.num_dup))
    log_helper.log_text('Number of Segments Delayed\t' + str(pld.num_delay))
    log_helper.log_text('Number of Retransmissions due to TIMEOUT\t' + str(num_retrans_timeout))
    log_helper.log_text('Number of FAST RETRANSMISSION\t' + str(num_retrans_fast))
    log_helper.log_text('Number of DUP ACKS received\t' + str(num_dup_ack))
    log_helper.log_text('=============================================================')
    log_helper.close()


if __name__ == '__main__':
    main()
