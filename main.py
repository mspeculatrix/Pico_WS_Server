"""
Pico 2W Asynchronous WebSockets-based Control Hub
Target Platform: RP2350 (Raspberry Pi Pico 2W) running MicroPython
Architecture: Cooperative concurrency via uasyncio, hardware-level interrupts,
non-blocking USB-Serial CLI, and a custom RFC 6455 WebSocket server.
"""

import sys

import network
import uasyncio as asyncio
import ubinascii
import uhashlib
import uselect

# ==============================================================================
# TYPE CHECKING GUARD (Static Analysis vs Embedded Runtime)
# ==============================================================================
# Standard MicroPython builds do not include the full Python 'typing' module
# to conserve flash storage and RAM. Importing it directly would cause an
# ImportError on the device. By using TYPE_CHECKING (which is False at
# runtime but True for tools like VS Code/Pylance), we enable strict static
# analysis during development while keeping the embedded execution clean.
try:
	from typing import TYPE_CHECKING
except ImportError:
	TYPE_CHECKING = False  # Default to False for runtime

if TYPE_CHECKING:
	from typing import Any, List, Optional

# ==============================================================================
# CONFIGURATION CONSTANTS & GLOBAL STATE
# ==============================================================================
WIFI_SSID = 'Minerva'
WIFI_PASSWORD = 'CezanneZola'
WS_PORT = 8080

# Track active WebSocket client stream writers for broadcasting telemetry
ACTIVE_CLIENTS: List[asyncio.StreamWriter] = []


# ==============================================================================
# CORE COMMAND ROUTER
# ==============================================================================
async def process_command(cmd_str: str) -> None:
	"""
	Parses and executes raw text commands received from either the local
	USB-Serial terminal or remote WebSocket clients.

	Currently supported commands:
	  - STATUS: Reports current system state and active PWM value.
	"""
	cmd_str = cmd_str.strip()

	if cmd_str == 'STATUS':
		await broadcast_status()
	else:
		print(f"[ROUTER] ERR: Unknown command: '{cmd_str}'")


# ==============================================================================
# ASYNCHRONOUS TASK 1: NON-BLOCKING USB-SERIAL CLI
# ==============================================================================
async def cli_task() -> None:
	"""
	Asynchronous task managing local interactive input over USB CDC Serial.

	Uses `uselect.poll()` to inspect `sys.stdin` non-blockingly. This prevents
	the REPL input reader from freezing the entire system event loop when
	the user isn't typing.

	Incoming bytes are stored in a buffer until a carriage return or newline is
	encountered, at which point the process_command() function is invoked and
	the buffer reset.
	"""
	poll_obj = uselect.poll()
	poll_obj.register(sys.stdin, uselect.POLLIN)

	buffer = ''
	print('[CLI] USB Serial CLI ready')

	while True:
		# Check input stream with zero timeout (non-blocking poll)
		if poll_obj.poll(0):
			char: str | Any = sys.stdin.read(1)
			if char:
				# Handle line termination (Enter key)
				if char == '\n' or char == '\r':
					if buffer:
						sys.stdout.write('\n')
						await process_command(buffer)
						buffer = ''
				# Handle backspace key code (ASCII 127)
				elif ord(char) == 127:
					if len(buffer) > 0:
						buffer = buffer[:-1]
						sys.stdout.write('\b \b')  # Visual terminal backspace
				else:
					sys.stdout.write(char)  # Local character echo
					buffer += char
		# Yield execution back to the uasyncio event loop for 20ms
		await asyncio.sleep_ms(20)


# ==============================================================================
# WEBSOCKET PROTOCOL & TELEMETRY BROADCASTING HELPERS
# ==============================================================================
async def send_ws_message(writer: asyncio.StreamWriter, message: str) -> None:
	"""
	Constructs an unmasked RFC 6455 WebSocket text frame and writes it
	to the client stream.
	"""
	payload: bytes = message.encode('utf-8')
	length: int = len(payload)

	# Header byte 0: 0x81 (FIN bit set + Text opcode)
	header = bytearray([0x81])

	# Header byte(s) 1+: Payload length encoding rules
	if length <= 125:
		header.append(length)
	elif length <= 65535:
		header.append(126)
		header.extend(length.to_bytes(2, 'big'))
	else:
		header.append(127)
		header.extend(length.to_bytes(8, 'big'))

	writer.write(header + payload)
	await writer.drain()


async def broadcast_message(msg) -> None:
	"""
	Broadcast a message to all connected clients.
	Basically a wrapper to send_ws_message()
	"""
	disconnected: list[Any] = []
	for client_writer in ACTIVE_CLIENTS:
		try:
			await send_ws_message(client_writer, msg)
		except Exception:
			disconnected.append(client_writer)

	# Clean up stale connections
	for dead_client in disconnected:
		if dead_client in ACTIVE_CLIENTS:
			ACTIVE_CLIENTS.remove(dead_client)

	# Also print to CLI
	print(msg)


async def broadcast_status() -> None:
	"""
	Formats system values into a JSON string and broadcasting to all active
	WebSocket clients.
	"""
	global ACTIVE_CLIENTS

	if not ACTIVE_CLIENTS:
		return

	# Build JSON message payload
	status_fmt: str = '{ "type": "status", "clients": %d }'
	status_json: str = status_fmt % (len(ACTIVE_CLIENTS))

	await broadcast_message(status_json)


def parse_websocket_frame(data: bytes) -> 'Optional[str]':
	"""
	Parses, checks opcodes, extracts payload lengths, and unmasks incoming
	client-to-server RFC 6455 WebSocket data frames.

	All client frames are XOR-masked using a 4-byte key for security; this
	function reverses that mask to recover the clean text payload.
	"""
	if len(data) < 2:
		return None

	# Byte 0: Flags and Opcode (Lower 4 bits)
	# Opcode 0x8 signals a connection close frame from the client.
	opcode: int = data[0] & 0x0F
	if opcode == 0x8:
		return 'CLOSE'

	# Byte 1: Mask flag (MSB) and Payload Length (Lower 7 bits)
	masked: bool = (data[1] & 0x80) != 0
	payload_len: int = data[1] & 0x7F

	idx = 2
	# Handle extended payload length framing standards
	if payload_len == 126:
		payload_len = int.from_bytes(data[2:4], 'big')
		idx = 4
	elif payload_len == 127:
		payload_len = int.from_bytes(data[2:10], 'big')
		idx = 10

	# Extract and unmask payload bytes if a masking key is present
	if masked:
		mask_key: bytes = data[idx : idx + 4]
		idx += 4
		encoded_payload: bytes = data[idx : idx + payload_len]

		# Apply cyclic XOR decoding using the 4-byte mask key
		decoded_bytes = bytes(
			b ^ mask_key[i % 4] for i, b in enumerate(encoded_payload)
		)
		return decoded_bytes.decode('utf-8')
	else:
		return data[idx : idx + payload_len].decode('utf-8')


async def websocket_handler(
	reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
	"""
	Manages individual client socket connections:
	1. Reads incoming HTTP headers and extracts the 'Sec-WebSocket-Key'.
	2. Computes the cryptographic RFC 6455 SHA-1 / Base64 acceptance hash token.
	3. Completes HTTP-to-WebSocket '101 Switching Protocols' upgrade handshake.
	4. Enters an async read loop to parse, unmask, and route incoming commands.
	"""
	global ACTIVE_CLIENTS
	addr: Any = writer.get_extra_info('peername')
	print(f'[WS] Client connected from {addr}')

	try:
		ws_key: Optional[bytes] = None

		# Read HTTP header lines sequentially until the empty CRLF delimiter
		while True:
			line: bytes = await reader.readline()
			if not line or line == b'\r\n':
				break
			if line.lower().startswith(b'sec-websocket-key:'):
				ws_key = line.split(b':')[1].strip()

		# Drop connection if client did not supply a valid WebSocket key
		if not ws_key:
			writer.close()
			return

		# Compute the standard RFC 6455 handshake accept token
		sha1 = uhashlib.sha1(ws_key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
		accept_key: bytes = ubinascii.b2a_base64(sha1.digest()).strip()

		# Construct and dispatch valid protocol upgrade headers back to client
		response: bytes = (
			b'HTTP/1.1 101 Switching Protocols\r\n'
			b'Upgrade: websocket\r\n'
			b'Connection: Upgrade\r\n'
			b'Sec-WebSocket-Accept: ' + accept_key + b'\r\n\r\n'
		)
		await writer.awrite(response)
		print('[WS] Handshake successful, connection established.')

		# Register client for telemetry broadcasting
		ACTIVE_CLIENTS.append(writer)

		# Active communication loop handling incoming frames
		while True:
			try:
				data: bytes = await reader.read(256)
				if not data:
					break

				message: str | None = parse_websocket_frame(data)
				if message == 'CLOSE':
					# Acknowledge the close frame back to the browser
					try:
						writer.write(
							bytearray([0x88, 0x00])
						)  # Standard empty close frame (Opcode 0x8)
						await writer.drain()
					except Exception:
						pass
					break

				if message:
					print(f'[RECV]: {message}')
					await process_command(message)
			except Exception:
				break
	except Exception as e:
		print(f'[WS ERROR] Connection dropped: {e}')
	finally:
		# Unregister client from active telemetry list
		if writer in ACTIVE_CLIENTS:
			ACTIVE_CLIENTS.remove(writer)

		# Close and release the stream socket back to lwIP
		try:
			writer.close()
			await writer.wait_closed()
		except Exception:
			pass

		print('[WS] Client disconnected.')


async def network_task() -> None:
	"""
	Asynchronous task managing Wi-Fi connection state and initiating the
	TCP server listener socket for incoming WebSocket clients.
	"""
	wlan = network.WLAN(network.STA_IF)
	wlan.active(True)

	print(f'[NET] Connecting to Wi-Fi SSID: {WIFI_SSID}...')
	wlan.connect(WIFI_SSID, WIFI_PASSWORD)

	# Wait for association with a 30-second timeout ceiling
	timeout = 30
	while not wlan.isconnected() and timeout > 0:
		await asyncio.sleep(1)
		timeout -= 1

	if not wlan.isconnected():
		print('[NET ERROR] Wi-Fi connection timed out!')
		return

	ip: str = wlan.ifconfig()[0]
	print(f'[NET] Connected successfully! Local IP: {ip}')

	# Bind and start the TCP socket server on designated port
	await asyncio.start_server(websocket_handler, '0.0.0.0', WS_PORT)
	print(f'[NET] WebSockets server listening on port {WS_PORT}')

	# Keep the network management task alive in the background
	while True:
		await asyncio.sleep(3600)


# ==============================================================================
# MAIN ENTRY POINT & EVENT LOOP INITIALIZATION
# ==============================================================================
async def main() -> None:
	"""
	Initializes hardware peripherals and schedules background tasks concurrently
	inside the primary uasyncio event loop.
	"""
	print('\n--- Pico WebSocket Server ---')

	# Create concurrent background tasks managed by the event loop
	asyncio.create_task(network_task())
	asyncio.create_task(cli_task())

	# Keep the root event loop spinning continuously
	while True:
		await asyncio.sleep(1)


# Execute event loop with graceful keyboard interruption handling
try:
	asyncio.run(main())
except KeyboardInterrupt:
	print('\nProgram interrupted by user. Shutting down...')
