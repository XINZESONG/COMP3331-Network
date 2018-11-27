import time

output_file = None
init_timestamp = 0


def init(file_name):
    global output_file
    global init_timestamp
    output_file = open(file_name, 'w')
    init_timestamp = time.time()


def close():
    if output_file is not None:
        output_file.close()


def log_packet(event, packet):
    if packet.isSyn:
        packet_type = 'S'
    elif packet.isAck:
        packet_type = 'A'
    elif packet.isFin:
        packet_type = 'F'
    else:
        packet_type = 'D'

    data_length = 0
    if packet.data is not None:
        data_length = len(packet.data)
    log_event(event, packet_type, packet.sequenceNum, data_length, packet.ackNum)


def log_event(event, packet_type, seq_number, number_of_data, ack_number):
    global init_timestamp

    log_text('\t'.join([event, '%.2f' % (time.time() - init_timestamp), packet_type, str(seq_number), str(number_of_data), str(ack_number)]))


def log_text(text):
    try:
        output_file.write(text + '\n')
    except:
        pass
