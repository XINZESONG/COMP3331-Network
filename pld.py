import random
from threading import Timer
import log_helper

argv_pDrop = 0.5
argv_pDuplicate = 0.5
argv_pCorrupt = 0.5
argv_pOrder = 0.5
argv_maxOrder = 6
argv_pDelay = 0.5
argv_maxDelay = 10  # ms
argv_seed = 1000


num_pld = 0
num_dropped = 0
num_corrupted = 0
num_reorder = 0
num_dup = 0
num_delay = 0


def config(pDrop, pDuplicate, pCorrupt, pOrder, maxOrder, pDelay, maxDelay, seed):
    global argv_pDrop
    global argv_pDuplicate
    global argv_pCorrupt
    global argv_pOrder
    global argv_maxOrder
    global argv_pDelay
    global argv_maxDelay
    global argv_seed

    argv_pDrop = pDrop
    argv_pDuplicate = pDuplicate
    argv_pCorrupt = pCorrupt
    argv_pOrder = pOrder
    argv_maxOrder = maxOrder
    argv_pDelay = pDelay
    argv_maxDelay = maxDelay
    argv_seed = seed
    random.seed(seed)


def rand_succeed(p):
    return random.random() <= p


def timer_callback(udp_socket, packet, address):
    try:
        udp_socket.sendto(packet.to_byte_array(), address)
        log_helper.log_packet('dely', packet)
    except:
        pass


reordered_packet = None
reordered_countdown = 0


def send_packet(udp_socket, packet, address):
    global argv_pDrop
    global argv_pDuplicate
    global argv_pCorrupt
    global argv_pOrder
    global argv_maxOrder
    global argv_pDelay
    global argv_maxDelay
    global argv_seed
    global reordered_packet
    global reordered_countdown

    # Statistics
    global num_pld
    global num_dropped
    global num_corrupted
    global num_reorder
    global num_dup
    global num_delay

    num_pld += 1
    if rand_succeed(argv_pDrop):
        num_dropped += 1
        # do nothing, drop the packet
        log_helper.log_packet('drop', packet)
    elif rand_succeed(argv_pDuplicate):
        num_dup += 1
        # duplicate the packet
        udp_socket.sendto(packet.to_byte_array(), address)
        udp_socket.sendto(packet.to_byte_array(), address)
        log_helper.log_packet('dup', packet)
    elif rand_succeed(argv_pCorrupt):
        num_corrupted += 1
        # Flip a bit
        correct_bytes = packet.to_byte_array()
        corrupted_index = random.randrange(0, len(correct_bytes))
        corrupted_byte = correct_bytes[corrupted_index]

        corrupted_bit_index = random.randrange(0, 8)
        # Bit flip
        if corrupted_byte >> corrupted_bit_index & 1 == 1:
            corrupted_byte &= ~(1 << corrupted_bit_index)
        else:
            corrupted_byte |= (1 << corrupted_bit_index)
        correct_bytes[corrupted_index] = corrupted_byte
        udp_socket.sendto(correct_bytes, address)
        log_helper.log_packet('corr', packet)
    elif rand_succeed(argv_pOrder):
        if reordered_packet is None:
            num_reorder += 1
            reordered_packet = packet
            reordered_countdown = argv_maxOrder
        else:
            udp_socket.sendto(packet.to_byte_array(), address)
            log_helper.log_packet('snd', packet)
    elif rand_succeed(argv_pDelay):
        num_delay += 1
        delay_time = random.randrange(0, argv_maxDelay)  # milliseconds
        r = Timer(delay_time / 1000.0, timer_callback, (udp_socket, packet, address))
        r.start()
    else:
        # send packet as normal
        udp_socket.sendto(packet.to_byte_array(), address)
        log_helper.log_packet('snd', packet)

    if reordered_packet is not None:
        reordered_countdown -= 1
        if reordered_countdown == 0:
            udp_socket.sendto(reordered_packet.to_byte_array(), address)
            log_helper.log_packet('rord', reordered_packet)
            reordered_packet = None
