#!/usr/bin/env python3
import socket
import threading
import argparse
import sys
import time
from protocol import Protocol, MessageType, CommandName, EventName

class ChatServer:
    def __init__(self, port, debug_level):
        self.port = port
        self.debug_level = debug_level
        self.server_socket = None
        self.running = False
        self.last_activity = time.time()
        self.idle_timeout = 180  # 3 minutes in seconds
        
        # Server state
        self.clients = {}  # {client_socket: {"nickname": str, "channels": set()}}
        self.channels = {}  # {channel_name: set(client_sockets)}
        self.client_lock = threading.Lock()
        
        # Thread pool
        self.max_threads = 4
        self.active_threads = 0
        self.thread_semaphore = threading.Semaphore(self.max_threads)
        
    def log(self, message, level=0):
        """Log messages based on debug level (0=errors only, 1=all events)"""
        if level <= self.debug_level:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {message}")
    
    def start(self):
        """Start the chat server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)  # Timeout for accept() to check running flag
            self.running = True
            
            self.log(f"ChatServer started on port {self.port}", 1)
            self.log(f"Debug level: {self.debug_level}", 1)
            self.log(f"Max threads: {self.max_threads}", 1)
            
            # Start idle checker thread
            idle_thread = threading.Thread(target=self._check_idle, daemon=True)
            idle_thread.start()
            
            # Main accept loop
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    self.log(f"New connection from {address}", 1)
                    self.last_activity = time.time()
                    
                    # Start client handler thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue  # Check running flag and continue
                except OSError:
                    if self.running:
                        self.log("Error accepting connection", 0)
                    break
                    
        except KeyboardInterrupt:
            self.log("\nReceived Ctrl-C, shutting down...", 1)
        except Exception as e:
            self.log(f"Server error: {e}", 0)
        finally:
            self.shutdown()
    
    def _check_idle(self):
        """Check for idle timeout and shutdown if needed"""
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            with self.client_lock:
                if len(self.clients) == 0:
                    idle_time = time.time() - self.last_activity
                    if idle_time > self.idle_timeout:
                        self.log(f"Server idle for {int(idle_time)} seconds, shutting down...", 1)
                        self.running = False
                        break
    
    def _handle_client(self, client_socket, address):
        """Handle a single client connection"""
        # Acquire thread semaphore (limit concurrent threads)
        self.thread_semaphore.acquire()
        
        try:
            with self.client_lock:
                self.clients[client_socket] = {
                    "nickname": f"user_{address[1]}",  # Default nickname
                    "channels": set(),
                    "address": address
                }
            
            self.log(f"Client handler started for {address}", 1)
            
            # Send welcome message
            welcome = Protocol.resp_connected(
                server_name=f"ChatServer:{self.port}",
                client_id=str(address[1]),
                motd="Welcome to the chat server!"
            )
            self._send_message(client_socket, welcome)
            
            # Buffer for incomplete messages
            buffer = ""
            
            while self.running:
                try:
                    # Receive data
                    data = client_socket.recv(4096).decode('utf-8')
                    if not data:
                        self.log(f"Client {address} disconnected", 1)
                        break
                    
                    buffer += data
                    
                    # Process complete messages (lines ending in \n)
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line:
                            self._process_message(client_socket, line + '\n')
                            self.last_activity = time.time()
                
                except socket.timeout:
                    continue
                except Exception as e:
                    self.log(f"Error handling client {address}: {e}", 0)
                    break
        
        finally:
            # Clean up client
            self._disconnect_client(client_socket)
            self.thread_semaphore.release()
    
    def _process_message(self, client_socket, line):
        """Process a single message from a client"""
        try:
            msg = Protocol.decode(line)
            self.log(f"Received: {msg}", 1)
            
            if msg.type != MessageType.COMMAND:
                self._send_error(client_socket, "unknown", "Expected command message")
                return
            
            # Route to command handlers
            if msg.name == CommandName.NICK:
                self._handle_nick(client_socket, msg)
            elif msg.name == CommandName.LIST:
                self._handle_list(client_socket, msg)
            elif msg.name == CommandName.JOIN:
                self._handle_join(client_socket, msg)
            elif msg.name == CommandName.LEAVE:
                self._handle_leave(client_socket, msg)
            elif msg.name == CommandName.MSG:
                self._handle_msg(client_socket, msg)
            elif msg.name == CommandName.HELP:
                self._handle_help(client_socket, msg)
            elif msg.name == CommandName.QUIT:
                self._handle_quit(client_socket, msg)
            else:
                self._send_error(client_socket, msg.name, "Unknown command")
        
        except ValueError as e:
            self.log(f"Invalid message: {e}", 0)
            self._send_error(client_socket, "unknown", "Invalid message format")
    
    def _handle_nick(self, client_socket, msg):
        """Handle /nick command"""
        nickname = msg.data.get("nickname", "").strip()
        
        # Validate nickname
        if not nickname or len(nickname) > 20 or not nickname.replace('_', '').isalnum():
            self._send_error(client_socket, CommandName.NICK, "Invalid nickname format")
            return
        
        # Check if nickname is taken
        with self.client_lock:
            for client, info in self.clients.items():
                if client != client_socket and info["nickname"] == nickname:
                    self._send_error(client_socket, CommandName.NICK, "Nickname already in use")
                    return
            
            # Set nickname
            self.clients[client_socket]["nickname"] = nickname
        
        self.log(f"Client set nickname to: {nickname}", 1)
        response = Protocol.resp_ok(CommandName.NICK, {"nickname": nickname})
        self._send_message(client_socket, response)
    
    def _handle_list(self, client_socket, msg):
        """Handle /list command"""
        with self.client_lock:
            channels = []
            for channel_name, members in self.channels.items():
                channels.append({
                    "name": channel_name,
                    "users": len(members)
                })
        
        response = Protocol.resp_list_channels(channels)
        self._send_message(client_socket, response)
    
    def _handle_join(self, client_socket, msg):
        """Handle /join command"""
        channel = msg.data.get("channel", "").strip()
        
        # Validate channel name
        if not channel or not channel.startswith('#') or len(channel) < 2:
            self._send_error(client_socket, CommandName.JOIN, "Invalid channel name")
            return
        
        with self.client_lock:
            # Create channel if it doesn't exist
            if channel not in self.channels:
                self.channels[channel] = set()
            
            # Add client to channel
            self.channels[channel].add(client_socket)
            self.clients[client_socket]["channels"].add(channel)
            
            nickname = self.clients[client_socket]["nickname"]
        
        self.log(f"{nickname} joined {channel}", 1)
        
        # Send success response
        response = Protocol.resp_ok(CommandName.JOIN, {"channel": channel})
        self._send_message(client_socket, response)
        
        # Broadcast join event to all users in channel
        join_event = Protocol.evt_user_joined(channel, nickname)
        self._broadcast_to_channel(channel, join_event, exclude=client_socket)
    
    def _handle_leave(self, client_socket, msg):
        """Handle /leave command"""
        channel = msg.data.get("channel")
        
        with self.client_lock:
            client_channels = self.clients[client_socket]["channels"]
            
            # If no channel specified, leave current channel (first one)
            if not channel:
                if client_channels:
                    channel = list(client_channels)[0]
                else:
                    self._send_error(client_socket, CommandName.LEAVE, "Not in any channel")
                    return
            
            # Remove client from channel
            if channel in client_channels:
                self.channels[channel].discard(client_socket)
                client_channels.remove(channel)
                
                # Remove empty channels
                if len(self.channels[channel]) == 0:
                    del self.channels[channel]
                
                nickname = self.clients[client_socket]["nickname"]
            else:
                self._send_error(client_socket, CommandName.LEAVE, "Not in that channel")
                return
        
        self.log(f"{nickname} left {channel}", 1)
        
        # Send success response
        response = Protocol.resp_ok(CommandName.LEAVE, {"channel": channel})
        self._send_message(client_socket, response)
        
        # Broadcast leave event
        leave_event = Protocol.evt_user_left(channel, nickname)
        self._broadcast_to_channel(channel, leave_event)
    
    def _handle_msg(self, client_socket, msg):
        """Handle chat message"""
        text = msg.data.get("text", "").strip()
        channel = msg.data.get("channel")
        
        if not text:
            return
        
        with self.client_lock:
            client_channels = self.clients[client_socket]["channels"]
            nickname = self.clients[client_socket]["nickname"]
            
            # If no channel specified, use first joined channel
            if not channel:
                if client_channels:
                    channel = list(client_channels)[0]
                else:
                    self._send_error(client_socket, CommandName.MSG, "Not in any channel")
                    return
            
            # Check if client is in the channel
            if channel not in client_channels:
                self._send_error(client_socket, CommandName.MSG, "Not in that channel")
                return
        
        self.log(f"[{channel}] {nickname}: {text}", 1)
        
        # Broadcast message to all users in channel
        message_event = Protocol.evt_message(channel, nickname, text)
        self._broadcast_to_channel(channel, message_event)
    
    def _handle_help(self, client_socket, msg):
        """Handle /help command"""
        commands = [
            "/connect <server> [port] - Connect to server",
            "/nick <nickname> - Set your nickname",
            "/list - List all channels",
            "/join <channel> - Join a channel",
            "/leave [channel] - Leave a channel",
            "/quit - Disconnect from server",
            "/help - Show this help message"
        ]
        response = Protocol.resp_help(commands)
        self._send_message(client_socket, response)
    
    def _handle_quit(self, client_socket, msg):
        """Handle /quit command"""
        reason = msg.data.get("reason", "Client quit")
        self.log(f"Client requested quit: {reason}", 1)
        
        response = Protocol.resp_ok(CommandName.QUIT)
        self._send_message(client_socket, response)
        
        # Client will be cleaned up in _handle_client
    
    def _send_message(self, client_socket, message):
        """Send a message to a specific client"""
        try:
            data = Protocol.encode(message)
            client_socket.sendall(data)
            self.log(f"Sent: {message}", 1)
        except Exception as e:
            self.log(f"Error sending message: {e}", 0)
    
    def _send_error(self, client_socket, command_name, error_msg):
        """Send an error response to a client"""
        error = Protocol.resp_error(command_name, error_msg)
        self._send_message(client_socket, error)
    
    def _broadcast_to_channel(self, channel, message, exclude=None):
        """Broadcast a message to all clients in a channel"""
        with self.client_lock:
            if channel in self.channels:
                for client_socket in self.channels[channel]:
                    if client_socket != exclude:
                        self._send_message(client_socket, message)
    
    def _disconnect_client(self, client_socket):
        """Clean up a disconnected client"""
        with self.client_lock:
            if client_socket in self.clients:
                client_info = self.clients[client_socket]
                nickname = client_info["nickname"]
                
                # Remove from all channels
                for channel in list(client_info["channels"]):
                    if channel in self.channels:
                        self.channels[channel].discard(client_socket)
                        
                        # Broadcast leave event
                        leave_event = Protocol.evt_user_left(channel, nickname)
                        self._broadcast_to_channel(channel, leave_event)
                        
                        # Remove empty channels
                        if len(self.channels[channel]) == 0:
                            del self.channels[channel]
                
                # Remove client
                del self.clients[client_socket]
                self.log(f"Client {nickname} disconnected and cleaned up", 1)
        
        try:
            client_socket.close()
        except:
            pass
    
    def shutdown(self):
        """Shutdown the server gracefully"""
        self.log("Shutting down server...", 1)
        self.running = False
        
        # Notify all clients
        shutdown_event = Protocol.evt_server_shutdown("Server shutting down")
        with self.client_lock:
            for client_socket in list(self.clients.keys()):
                try:
                    self._send_message(client_socket, shutdown_event)
                    client_socket.close()
                except:
                    pass
            self.clients.clear()
            self.channels.clear()
        
        # Close server socket
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        self.log("Server shutdown complete", 1)


def main():
    parser = argparse.ArgumentParser(description='Chat Server')
    parser.add_argument('-p', '--port', type=int, required=True, help='Port number')
    parser.add_argument('-d', '--debug', type=int, choices=[0, 1], default=0, 
                        help='Debug level (0=errors only, 1=all events)')
    
    args = parser.parse_args()
    
    server = ChatServer(args.port, args.debug)
    server.start()


if __name__ == '__main__':
    main()