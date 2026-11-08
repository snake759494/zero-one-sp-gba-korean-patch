"""GBA BIOS LZ10 compressor (VRAM-safe: back-reference distance >= 2)."""

def lz10_compress(data, pad4=True):
    data = bytes(data)
    n = len(data)
    out = bytearray(b'\x10' + n.to_bytes(3, 'little'))
    table = {}
    i = 0
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n:
                break
            best_len = 0; best_dist = 0
            if i + 3 <= n:
                cands = table.get(data[i:i + 3])
                if cands:
                    maxlen = min(18, n - i)
                    for j in reversed(cands):
                        d = i - j
                        if d > 4096:
                            break
                        if d < 2:
                            continue
                        l = 3
                        while l < maxlen and data[j + l] == data[i + l]:
                            l += 1
                        if l > best_len:
                            best_len = l; best_dist = d
                            if l == maxlen:
                                break
            step = best_len if best_len >= 3 else 1
            if best_len >= 3:
                flags |= 0x80 >> bit
                v = (best_len - 3) << 12 | (best_dist - 1)
                out += bytes((v >> 8, v & 0xff))
            else:
                out.append(data[i])
            for k in range(i, i + step):
                if k + 3 <= n:
                    lst = table.setdefault(data[k:k + 3], [])
                    lst.append(k)
                    if len(lst) > 64:
                        del lst[:32]
            i += step
        out[flag_pos] = flags
    if pad4:
        out += b'\0' * (-len(out) % 4)
    return bytes(out)
