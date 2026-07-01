import serial, time

elm = serial.Serial("COM8", 38400, timeout=2)

def AT(cmd):
    elm.reset_input_buffer()
    elm.write((cmd + '\r').encode('ascii'))
    buf = b""
    while True:
        ch = elm.read(1)
        if not ch:
            break
        if ch == b">":
            break
        buf += ch
    return buf.decode(errors="ignore").replace("\r", " ").strip()

# ATZ, ATE0, ATL0, ATI, ATRV, AT@1

print("ATZ", AT("ATZ")) # reset all
time.sleep(1)
print("Echo off", AT("ATE0"))
print("Linefeeds off", AT("ATL0"))
print("Version ID", AT("ATI"))
print("Voltage Read", AT("ATRV"))
print("Device specs", AT("AT@1"))
print(30 * "-")

#print("protocol", AT("ATSP6"))
#print("AID prezente", AT("0010"))
#print("RPM brut", AT("010C"))

print("protocol 0100", AT("0100"))
print("protocol 0120", AT("0120"))
print("protocol 0140", AT("0140"))
print("protocol 0160", AT("0160"))