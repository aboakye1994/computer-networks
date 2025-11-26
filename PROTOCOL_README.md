# Chat Protocol

Object-based communication protocol for the chat server/client system using newline-delimited JSON (NDJSON).

## Overview

This protocol provides a simple, text-based messaging format for client-server communication. All messages are JSON objects sent over TCP sockets, terminated by newlines.

## Message Structure

Every message has three fields:

```json
{
  "type": "command|response|event",
  "name": "message_name",
  "data": { /* message-specific fields */ }
}
```

## Message Types

### Commands (Client → Server)
- `connect` - Connect to server
- `nick` - Set nickname
- `list` - List channels
- `join` - Join a channel
- `leave` - Leave a channel
- `msg` - Send chat message
- `help` - Get help
- `quit` - Disconnect

### Responses (Server → Client)
- Success: `{"status": "ok", ...}`
- Error: `{"status": "error", "error": "message", ...}`

### Events (Server → Client)
- `message` - Chat message broadcast
- `user_joined` - User joined channel
- `user_left` - User left channel
- `server_shutdown` - Server shutting down

## Quick Start

```python
from protocol import Protocol, Message

# Create a command
msg = Protocol.cmd_join("#general")

# Encode for network transmission
data = Protocol.encode(msg)  # Returns bytes ending in \n

# Send over socket
sock.sendall(data)

# Receive and decode
line = sock.recv(4096)  # Read until \n
msg = Protocol.decode(line)

# Check message type
if msg.type == MessageType.RESPONSE:
    if msg.data.get("status") == "ok":
        print("Success!")
```

## Wire Format

Messages are sent as newline-delimited JSON:

```
{"type":"command","name":"join","data":{"channel":"#general"}}\n
{"type":"response","name":"join","data":{"status":"ok"}}\n
{"type":"event","name":"message","data":{"channel":"#general","from":"Alice","text":"Hello!"}}\n
```

## Examples

### Client connects and joins a channel

```python
# 1. Connect
msg = Protocol.cmd_connect("chat.example.com", 6667)
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"connect","data":{"status":"ok","server":"chat.example.com","client_id":"client-123"}}

# 2. Set nickname
msg = Protocol.cmd_nick("Alice")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"nick","data":{"status":"ok"}}

# 3. Join channel
msg = Protocol.cmd_join("#general")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"join","data":{"status":"ok"}}

# 4. Send message
msg = Protocol.cmd_msg("Hello everyone!")
sock.sendall(Protocol.encode(msg))

# All users receive: {"type":"event","name":"message","data":{"channel":"#general","from":"Alice","text":"Hello everyone!"}}
```

### Error handling

```python
msg = Protocol.cmd_nick("@invalid@")
sock.sendall(Protocol.encode(msg))

# Receive: {"type":"response","name":"nick","data":{"status":"error","error":"Invalid nickname format"}}
```

## Validation Rules

- **Nicknames**: 1-20 characters, alphanumeric and underscores only
- **Channel names**: Must start with `#`, 2-50 characters
- **Messages**: No embedded newlines, max 512 bytes recommended

## Implementation Notes

- **Encoding**: UTF-8
- **Line terminator**: `\n` (newline)
- **Buffering**: Socket reads may be partial; buffer until `\n` is found
- **Message size**: Keep under 4KB for reliability
- **Text content**: Must not contain literal newlines (escape or reject)

## API Reference

### Factory Methods

```python
# Commands
Protocol.cmd_connect(server, port=6667)
Protocol.cmd_nick(nickname)
Protocol.cmd_list()
Protocol.cmd_join(channel)
Protocol.cmd_leave(channel=None)
Protocol.cmd_msg(text, channel=None)
Protocol.cmd_help()
Protocol.cmd_quit(reason=None)

# Responses
Protocol.resp_ok(command_name, data=None)
Protocol.resp_error(command_name, error_msg, data=None)
Protocol.resp_connected(server_name, client_id, motd=None)
Protocol.resp_list_channels(channels)
Protocol.resp_help(commands)

# Events
Protocol.evt_message(channel, sender, text, timestamp=None)
Protocol.evt_user_joined(channel, username)
Protocol.evt_user_left(channel, username)
Protocol.evt_server_shutdown(reason=None)
```

## Testing

```python
# Test serialization
msg = Protocol.cmd_join("#test")
print(msg.to_dict())
# {'type': 'command', 'name': 'join', 'data': {'channel': '#test'}}

# Test encoding/decoding
encoded = Protocol.encode(msg)
decoded = Protocol.decode(encoded)
assert decoded.name == "join"
assert decoded.data["channel"] == "#test"
```
```

## License

Created for CSC4220/6220 Computer Networks Team Project.
