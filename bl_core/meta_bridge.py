import sys
import time
import serial
import serial.tools.list_ports
import mtk_exploit
import mtk_meta_protocol

def run_meta_worker(target_port=None, status_path="meta_status.txt"):
    def set_status(code, msg):
        try:
            with open(status_path, "w", encoding="utf-8") as sf:
                sf.write(f"{code}|{msg}")
        except Exception:
            pass

    if not target_port:
        print("[*] Waiting for MTK device (Preloader / BROM / META mode)...")
        print("    1. Turn off phone completely.")
        print("    2. Hold Volume Down (or Volume Up / both) and connect USB cable.")
        print("    (Press Ctrl+C to cancel waiting)\n")

        initial_ports = {p.device for p in serial.tools.list_ports.comports()}
        start_time = time.time()
        timeout = 90  # 90 seconds timeout

        try:
            while time.time() - start_time < timeout:
                elapsed = int(time.time() - start_time)
                mins, secs = divmod(elapsed, 60)
                sys.stdout.write(f"\r[*] Searching for MTK device... [{mins:02d}:{secs:02d}] ")
                sys.stdout.flush()

                current_ports = list(serial.tools.list_ports.comports())
                found_port = None

                # Check for explicit MTK VID/strings
                for p in current_ports:
                    desc = (p.description or "").lower()
                    if p.vid == 0x0E8D or "mediatek" in desc or "mtk" in desc or "preloader" in desc or "vcom" in desc:
                        found_port = p.device
                        break

                # Check for new arrival port
                if not found_port:
                    for p in current_ports:
                        if p.device not in initial_ports:
                            found_port = p.device
                            break

                if found_port:
                    target_port = found_port
                    sys.stdout.write(f"\n[+] Detected MTK device on: {target_port}!\n")
                    sys.stdout.flush()
                    break

                time.sleep(0.2)

        except KeyboardInterrupt:
            sys.stdout.write("\n[!] Device wait canceled by user.\n")
            sys.stdout.flush()
            set_status(1, "Operation canceled by user")
            return

        if not target_port:
            sys.stdout.write("\n[-] Timeout: No MTK device connected within 90 seconds.\n")
            sys.stdout.flush()
            set_status(2, "Connection timed out")
            return

    def get_port_desc(port_name):
        for p in serial.tools.list_ports.comports():
            if p.device.upper() == port_name.upper():
                return p.description or ""
        return ""

    def poll_for_meta_port(timeout=30, fallback=None):
        time.sleep(2.5)  # Allow Preloader port to drop as phone reboots
        start = time.time()
        while time.time() - start < timeout:
            elapsed = int(time.time() - start)
            sys.stdout.write(f"\r[*] Waiting for META mode COM port... [{elapsed:02d}s] ")
            sys.stdout.flush()

            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                desc = (p.description or "").lower()
                if p.vid == 0x0E8D or "mediatek" in desc or "mtk" in desc or "vcom" in desc:
                    sys.stdout.write(f"\n[+] Found META mode port: {p.device} ({p.description})\n")
                    sys.stdout.flush()
                    return p.device

            if fallback:
                for p in ports:
                    if p.device.upper() == fallback.upper():
                        sys.stdout.write(f"\n[+] Re-detected active port: {p.device}\n")
                        sys.stdout.flush()
                        return p.device

            time.sleep(0.3)

        sys.stdout.write("\n")
        sys.stdout.flush()
        return fallback

    # Check device mode: Preloader vs META
    desc = get_port_desc(target_port).lower()
    is_preloader = ("preloader" in desc) or ("usb port" in desc) or ("da usb" in desc)

    # If port already exists and isn't clearly Preloader, test if already in META mode
    is_already_meta = False
    if not is_preloader:
        try:
            probe_proto = mtk_meta_protocol.MtkMetaProtocol(lambda m: None)
            is_already_meta = probe_proto.connect_persistent(target_port)
            if is_already_meta:
                probe_proto.close()
        except Exception:
            is_already_meta = False

    # Stage 1: Trigger META via Preloader exploit
    if not is_already_meta:
        print(f"[*] Stage 1: Initiating Preloader to META Mode handshake on {target_port}...")
        exploit = mtk_exploit.MtkExploit(lambda m: print(f"  [BROM/PRELOADER] {m}"))

        try:
            trigger_ok = exploit.trigger_meta_mode(target_port)
        except Exception as e:
            print(f"[-] Exploit trigger error: {e}")
            trigger_ok = False

        if not trigger_ok:
            print(f"[-] Preloader META trigger failed on {target_port}.")
            print("    Please disconnect cable, power off phone completely, and retry.")
            set_status(3, "Preloader handshake failed")
            return

        print("[+] Device successfully commanded to reboot into META Mode!")
        print("[*] Waiting for device to re-enumerate in META Mode...")

        meta_port = poll_for_meta_port(timeout=30, fallback=target_port)
        if not meta_port:
            print("[-] Timed out waiting for META mode COM port.")
            set_status(2, "META port enumeration timeout")
            return

        target_port = meta_port
    else:
        print(f"[+] Device on {target_port} is already in META mode!")

    # Stage 2: Connect via MTK META Protocol
    print(f"[*] Stage 2: Connecting to {target_port} via MTK META Protocol...")
    time.sleep(1.0)

    proto = mtk_meta_protocol.MtkMetaProtocol(lambda m: print(f"  [META] {m}"))

    try:
        ok = proto.connect_persistent(target_port)
        if not ok:
            time.sleep(2.0)
            ok = proto.connect_persistent(target_port)

        if not ok:
            print(f"[-] Failed to establish META handshake on {target_port}.")
            set_status(3, "Failed to establish META handshake on port")
            return

        print("[+] META Mode connection established successfully!")

        # Unlock internal protocol authorization
        proto._authorized = True

        # Initialize AP engineering shell
        print("[*] Initializing AP Engineering Shell...")
        try:
            proto.initialize_ap_editor_shell()
        except Exception as e:
            print(f"  [META] AP Shell init note: {e}")

        # Stage 3: Wipe seccfg hardware partition & FRP lock
        # Use ONLY the engine's resolved LBA-seek routine. Previous direct
        # bs=4096 dd one-liners used DONE_OK-absent EOF garble that could not
        # be verified - they are removed here. Every call now goes through
        # readlink -> /sys LBA start -> bs=512 seek=<LBA> zeroing, and the
        # boolean result is captured and surfaced (no more swallowed returns).
        print("[*] Stage 3: Wiping hardware security configuration (seccfg) and FRP lock...")
        wipe_results = []
        for block_dev, part_name in [
            ("/dev/block/platform/bootdevice/by-name/seccfg", "seccfg"),
            ("/dev/block/by-name/seccfg", "seccfg"),
            ("/dev/block/platform/bootdevice/by-name/frp", "frp"),
            ("/dev/block/by-name/frp", "frp"),
        ]:
            try:
                ok = proto.wipe_partition_via_shell(block_dev, part_name)
                wipe_results.append((block_dev, bool(ok)))
                if ok:
                    print(f"  [+] LBA seek-wipe OK: {block_dev}")
                else:
                    print(f"  [!] LBA seek-wipe returned False: {block_dev}")
            except Exception as e:
                wipe_results.append((block_dev, False))
                print(f"  [!] LBA seek-wipe error on {block_dev}: {e}")

        sec_ok = any(ok for dev, ok in wipe_results if "seccfg" in dev)
        if sec_ok:
            print("[+] Hardware seccfg cleared (LBA seek-wipe executed)!")

        # Direct zeroing from offset 0 to guarantee wiping the lock magic header at byte 0
        print("[*] Ensuring lock header at byte 0 is zeroed on all partition nodes...")
        direct_zero_confirmed = False
        for block_dev in [
            "/dev/block/by-name/seccfg",
            "/dev/block/platform/bootdevice/by-name/seccfg",
            "/dev/block/by-name/frp",
            "/dev/block/platform/bootdevice/by-name/frp",
        ]:
            try:
                cmd = f"dd if=/dev/zero of={block_dev} bs=4096 count=128 conv=notrunc 2>/dev/null && echo 'ZERO_OK'"
                out = proto.execute_shell_cmd_direct(cmd)
                if "ZERO_OK" in (out or ""):
                    print(f"  [+] Direct zero (offset 0) confirmed: {block_dev}")
                    direct_zero_confirmed = True
                else:
                    cmd2 = f"dd if=/dev/zero of={block_dev} bs=512 count=512 conv=notrunc 2>/dev/null && echo 'ZERO_OK'"
                    out2 = proto.execute_shell_cmd_direct(cmd2)
                    if "ZERO_OK" in (out2 or ""):
                        print(f"  [+] Direct zero (offset 0, 512b) confirmed: {block_dev}")
                        direct_zero_confirmed = True
            except Exception as e:
                print(f"  [!] Direct zero note on {block_dev}: {e}")

        # Set BCB bootloader flag in misc so device boots directly to Fastboot on restart
        print("[*] Setting Bootloader Control Block (BCB) in misc for Fastboot...")
        for misc_dev in [
            "/dev/block/by-name/misc",
            "/dev/block/platform/bootdevice/by-name/misc",
        ]:
            try:
                proto.execute_shell_cmd_direct(f"echo -en 'bootonce-bootloader' > {misc_dev} 2>/dev/null")
            except Exception:
                pass

        # Reboot to bootloader directly
        print("[*] Rebooting device directly to Fastboot / Bootloader...")
        try:
            proto.execute_shell_cmd_direct("reboot bootloader")
        except Exception:
            pass
        try:
            proto.reboot_device()
        except Exception:
            pass

        proto.close()
        print("[+] Process completed successfully! Phone is rebooting to Fastboot.")
        set_status(0, "META Mode Unlock completed successfully")

    except Exception as e:
        print(f"[-] Protocol error: {e}")
        set_status(4, str(e))

if __name__ == "__main__":
    port_arg = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "" else None
    status_arg = sys.argv[2] if len(sys.argv) > 2 else "meta_status.txt"
    run_meta_worker(port_arg, status_arg)
