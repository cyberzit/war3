"""Bounded allocator graph inspection for the pinned local experiment.

No process writes. A free-list head is a graph root, not an independent counter.
"""
import struct
import copy

ACTIVE = 0xfffffffe
END = 0xffffffff


def free_chain(entries, head):
    chain, seen = [], set()
    while head != END:
        if not 0 <= head < len(entries) or head in seen:
            raise ValueError('Allocator free list has an invalid index or cycle')
        if entries[head][0] == ACTIVE:
            raise ValueError('Allocator free list references an active object')
        seen.add(head)
        chain.append(head)
        head = entries[head][0]
    free = {i for i, entry in enumerate(entries) if entry[0] != ACTIVE}
    if seen != free:
        raise ValueError('Allocator free list does not cover exactly the free entries')
    return chain


def snapshot(address, read):
    def word(offset):
        return int.from_bytes(read(address + offset, 4), 'little')
    count, head, serial, table = word(0x1c), word(0x40), word(0x50), word(0xc)
    if count > 100000:
        raise ValueError('Allocator table exceeds diagnostic bound')
    entries = []
    for first in range(0, count, 128):
        raw = read(table + first*8, min(128, count-first)*8)
        entries.extend([list(pair) for pair in struct.iter_unpack('<II', raw)])
    if (count, head, serial, table) != (word(0x1c), word(0x40), word(0x50), word(0xc)):
        raise ValueError('Allocator changed during capture')
    return {'address': address, 'table_address': table, 'count': count,
            'head': head, 'serial': serial, 'entries': entries,
            'free_chain': free_chain(entries, head)}


def listener_key(detail):
    if detail.get('vtable_rva') != '0x952b6c':
        raise ValueError('Only pinned internal threshold listeners are supported')
    words = struct.unpack('<32I', bytes.fromhex(detail['header']))
    if words[3:5] != (0x5e6c6973, 0x6072746c):
        raise ValueError('Unexpected listener type tags')
    owner = struct.unpack('<32I', bytes.fromhex(detail['listener_links']['0x30']['header']))
    prop = struct.unpack('<32I', bytes.fromhex(detail['listener_links']['0x40']['header']))
    return (owner[5], owner[6], prop[5], prop[6], *words[17:21])


def relocate_listeners(donor, target):
    """Plan a graph-preserving relocation, never just overwrite its head/count.

    All destinations must be free. Keep target object pointers and intrusive
    links; replace only the allocator identity of a uniquely matched listener.
    Swap each vacated slot into the destination's old free-list position.
    The allocator serial high-water mark is deliberately NOT reduced.
    """
    source = donor['sync_allocator_graph']
    graph = target['sync_allocator_graph']
    free_chain(source['entries'], source['head'])
    free_chain(graph['entries'], graph['head'])
    if source['count'] != graph['count']:
        raise ValueError('Different allocator capacities')
    def keyed(snapshot):
        result = {}
        for index, detail in snapshot['sync_object_details'].items():
            key = listener_key(detail)
            if key in result:
                raise ValueError('Ambiguous listener semantic identity')
            result[key] = (int(index), detail)
        return result
    a, b = keyed(donor), keyed(target)
    if not a or a.keys() != b.keys():
        raise ValueError('Listener sets do not match exactly')
    output = copy.deepcopy(graph)
    moves, permutation = [], {}
    for key in sorted(a):
        destination, original = a[key]
        old, current = b[key]
        if old == destination:
            raise ValueError('Expected only displaced listeners')
        if graph['entries'][destination][0] == ACTIVE:
            raise ValueError('Destination is occupied')
        old_words = struct.unpack('<32I', bytes.fromhex(current['header']))
        donor_words = struct.unpack('<32I', bytes.fromhex(original['header']))
        pointer = int(current['address'], 16)
        if graph['entries'][old] != [ACTIVE, pointer] or old_words[5] != old:
            raise ValueError('Target object identity disagrees with allocator')
        if source['entries'][destination] != [ACTIVE, int(original['address'], 16)] or donor_words[5] != destination:
            raise ValueError('Donor object identity disagrees with allocator')
        if donor_words[6] >= graph['serial']:
            raise ValueError('Restored identity exceeds target serial high-water mark')
        permutation[old], permutation[destination] = destination, old
        moves.append({'old': old, 'destination': destination, 'pointer': pointer,
                      'before_serial': old_words[6], 'serial': donor_words[6],
                      'semantic_key': list(key)})
    if len(permutation) != len(moves)*2:
        raise ValueError('Overlapping relocations')
    for index, (tag, pointer) in enumerate(graph['entries']):
        target_index = permutation.get(index, index)
        output['entries'][target_index] = [permutation.get(tag, tag), pointer]
    output['head'] = permutation.get(graph['head'], graph['head'])
    output['free_chain'] = free_chain(output['entries'], output['head'])
    if output['free_chain'] != [permutation.get(i, i) for i in graph['free_chain']]:
        raise ValueError('Relocation changed allocator topology')
    return output, moves
