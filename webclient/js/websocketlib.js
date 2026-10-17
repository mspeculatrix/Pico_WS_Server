/**
 * @file websocketlib.js
 * @brief Some handy functions for working with WebSockets.
 */

let socket = null

function wsSocketConnect(receiveFunc, ip, port, route = '') {
    // Only attempt connection if we aren't already connected or connecting
    if (ip !== '' && socket === null) {
        let url = 'ws://' + ip + ':' + port
        if (route !== '') {
            url += '/' + route
        }

        socket = new WebSocket(url)

        socket.onopen = () => {
            console.log('WebSocket connection open.')
        }

        socket.onmessage = receiveFunc

        socket.onclose = (event) => {
            console.log('WebSocket closed - code:', event.code, 'reason:', event.reason)
            socket = null
        }

        socket.onerror = (error) => {
            console.error('WebSocket error:', error)
        }
    }
}

function wsSocketDisconnect() {
    if (socket !== null) {
        console.log('Closing socket connection manually.')
        socket.close()
    }
}

function wsSocketSend(msg) {
    let msgSent = false
    if (socket !== null) {
        // WebSocket.OPEN is equivalent to readyState === 1
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(msg)
            msgSent = true
        } else {
            console.warn('Socket is not open. Ready state is:', socket.readyState)
        }
    }
    return msgSent
}

function wsSocketState() {
    /*
    Possible states are:

    WebSocket.CONNECTING (0)
    Socket has been created. The connection is not yet open.

    WebSocket.OPEN (1)
    The connection is open and ready to communicate.

    WebSocket.CLOSING (2)
    The connection is in the process of closing.

    WebSocket.CLOSED (3)
    The connection is closed or couldn't be opened.
    */
	if (socket !== null) {
		return socket.readyState
	}
	return WebSocket.CLOSED
}