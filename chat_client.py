#!/usr/bin/env python3
import socket
import threading
import sys
import signal

from protocol import (
    Protocol,
    MessageType,
    CommandName,
    EventName,
)

DEFAULT_PORT = 6667  # default port for /connect <server>


class ChatClient:
    def __init__(self):
        self.sock = None
        self.sock_file = None  # for readline()
        self.recv_thread = None
        self.running = False

        self.current_channel = None
        self.nickname = None
        self.client_id = None
        self.server_name = None

    # low-level connection 

    def connect(self, host, port):
        if self.sock is not None:
            print("[WARN] Already connected. Use /quit to disconnect first.")
            return

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            # text-mode reader; we still send bytes manually
            self.sock_file = self.sock.makefile("rb")
            self.running = True

            # Start receiver thread
            self.recv_thread = threading.Thread(
                target=self.recv_loop, daemon=True
            )
            self.recv_thread.start()

            print(f"[INFO] TCP connection established to {host}:{port}")

            # Send logical /connect command as defined in your protocol
            msg = Protocol.cmd_connect(host, port)
            self.send_message(msg)

        except Exception as e:
            print(f"[ERROR] Failed to connect: {e}")
            self.cleanup()

    def cleanup(self):
        self.running = False
        if self.sock_file is not None:
            try:
                self.sock_file.close()
            except Exception:
                pass
            self.sock_file = None

        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def disconnect(self):
        self.cleanup()
        print("[INFO] Disconnected from server.")

    # sending & receiving

    def send_message(self, msg):
        """Send a Message instance using Protocol.encode()."""
        if not self.sock:
            print("[ERROR] Not connected. Use /connect first.")
            return
        try:
            data = Protocol.encode(msg)
            self.sock.sendall(data)
        except Exception as e:
            print(f"[ERROR] Failed to send data: {e}")
            self.disconnect()

    def recv_loop(self):
        """Background thread to receive lines from the server."""
        while self.running and self.sock_file:
            try:
                line = self.sock_file.readline()
                if not line:
                    # EOF -> server closed connection
                    print("\n[INFO] Server closed the connection.")
                    self.disconnect()
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    msg = Protocol.decode(line)
                except ValueError as e:
                    print(f"[WARN] Invalid message from server: {e}")
                    continue

                self.handle_incoming(msg)

            except Exception as e:
                if self.running:
                    print(f"\n[ERROR] Receive loop error: {e}")
                self.disconnect()
                break

    # handling incoming messages

    def handle_incoming(self, msg):
        """Dispatch based on MessageType and name."""
        if msg.type == MessageType.RESPONSE:
            self.handle_response(msg)
        elif msg.type == MessageType.EVENT:
            self.handle_event(msg)
        else:
            print(f"[INFO] Server sent: {msg}")

    def handle_response(self, msg):
        """Handle responses (to commands we sent)."""
        name = msg.name
        data = msg.data or {}
        status = data.get("status")

        if status == "error":
            err = data.get("error", "Unknown error")
            print(f"[ERROR] {name}: {err}")
            return

        if name == CommandName.CONNECT.value:
            self.server_name = data.get("server")
            self.client_id = data.get("client_id")
            motd = data.get("motd")
            print(f"[INFO] Connected to server '{self.server_name}' as client {self.client_id}")
            if motd:
                print(f"[MOTD] {motd}")

        elif name == CommandName.LIST.value:
            channels = data.get("channels", [])
            print("[INFO] Channels:")
            for ch in channels:
                cname = ch.get("name", "")
                users = ch.get("users", 0)
                print(f"  {cname} ({users} users)")

        elif name == CommandName.HELP.value:
            commands = data.get("commands", [])
            print("[INFO] Available commands from server:")
            for line in commands:
                print(f"  {line}")

        elif name == CommandName.NICK.value:
            nick = data.get("nickname")
            if nick:
                self.nickname = nick
                print(f"[INFO] Nickname set to {nick}")
            else:
                print("[INFO] Nickname updated.")

        elif name == CommandName.JOIN.value:
            ch = data.get("channel")
            if ch:
                self.current_channel = ch
                print(f"[INFO] Joined channel {ch}")
            else:
                print("[INFO] Join success.")

        elif name == CommandName.LEAVE.value:
            ch = data.get("channel")
            if ch and self.current_channel == ch:
                self.current_channel = None
                print(f"[INFO] Left channel {ch}")
            else:
                print("[INFO] Leave success.")

        elif name == CommandName.QUIT.value:
            print("[INFO] Quit acknowledged by server.")

        else:
            print(f"[INFO] {name} OK: {data}")

    def handle_event(self, msg):
        """Handle async events broadcast by the server."""
        name = msg.name
        data = msg.data or {}

        if name == EventName.MESSAGE.value:
            channel = data.get("channel", "")
            sender = data.get("from", "<?>")
            text = data.get("text", "")
            if channel:
                print(f"[{channel}] {sender}: {text}")
            else:
                print(f"{sender}: {text}")

        elif name == EventName.USER_JOINED.value:
            channel = data.get("channel", "")
            user = data.get("user", "")
            print(f"[INFO] {user} joined {channel}")

        elif name == EventName.USER_LEFT.value:
            channel = data.get("channel", "")
            user = data.get("user", "")
            print(f"[INFO] {user} left {channel}")

        elif name == EventName.SERVER_SHUTDOWN.value:
            reason = data.get("reason", "Server is shutting down.")
            print(f"[INFO] SERVER_SHUTDOWN: {reason}")
            self.disconnect()

        else:
            print(f"[INFO] Event {name}: {data}")

    # user input handling 

    def process_input_line(self, line):
        line = line.strip()
        if not line:
            return

        if line.startswith("/"):
            parts = line[1:].split()
            if not parts:
                return
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd == "connect":
                if len(args) < 1:
                    print("Usage: /connect <server-name> [port]")
                    return
                host = args[0]
                port = int(args[1]) if len(args) > 1 else DEFAULT_PORT
                self.connect(host, port)
                return

            if cmd == "help":
                if not self.sock:
                    self.print_local_help()
                    return
                msg = Protocol.cmd_help()
                self.send_message(msg)
                return

            if cmd == "nick":
                if len(args) != 1:
                    print("Usage: /nick <nickname>")
                    return
                nick = args[0]
                msg = Protocol.cmd_nick(nick)
                self.send_message(msg)
                return

            if cmd == "list":
                if not self.sock:
                    print("[ERROR] Not connected.")
                    return
                msg = Protocol.cmd_list()
                self.send_message(msg)
                return

            if cmd == "join":
                if not self.sock:
                    print("[ERROR] Not connected.")
                    return
                if len(args) != 1:
                    print("Usage: /join <channel>")
                    return
                channel = args[0]
                msg = Protocol.cmd_join(channel)
                self.send_message(msg)
                self.current_channel = channel
                return

            if cmd == "leave":
                if not self.sock:
                    print("[ERROR] Not connected.")
                    return
                channel = args[0] if len(args) >= 1 else None
                msg = Protocol.cmd_leave(channel)
                self.send_message(msg)
                if channel is None or self.current_channel == channel:
                    self.current_channel = None
                return

            if cmd == "quit":
                reason = " ".join(args) if args else None
                if self.sock:
                    msg = Protocol.cmd_quit(reason)
                    self.send_message(msg)
                self.disconnect()
                sys.exit(0)

            print(f"[ERROR] Unknown command '/{cmd}'. Type /help.")
            return

        # plain chat text
        if not self.sock:
            print("[ERROR] Not connected. Use /connect first.")
            return
        if not self.current_channel:
            print("[ERROR] You are not in any channel. Use /join <channel>.")
            return

        msg = Protocol.cmd_msg(line, channel=self.current_channel)
        self.send_message(msg)

    def print_local_help(self):
        print("Local commands:")
        print("  /connect <server-name> [port]   Connect to a server")
        print("  /nick <nickname>                Set your nickname")
        print("  /list                           List channels")
        print("  /join <channel>                 Join a channel")
        print("  /leave [<channel>]              Leave current or given channel")
        print("  /help                           Ask server for help text")
        print("  /quit [reason]                  Quit the client")

    # run loop

    def run(self):
        print("Simple Chat Client")
        print("Type /help for commands.")
        while True:
            try:
                line = input("> ")
            except EOFError:
                print("\n[INFO] EOF received, quitting...")
                if self.sock:
                    msg = Protocol.cmd_quit("EOF")
                    self.send_message(msg)
                self.disconnect()
                break
            self.process_input_line(line)


def main():
    client = ChatClient()

    def signal_handler(sig, frame):
        print("\n[INFO] Ctrl-C detected, quitting...")
        if client.sock:
            msg = Protocol.cmd_quit("Ctrl-C")
            client.send_message(msg)
        client.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    client.run()


if __name__ == "__main__":
    main()
