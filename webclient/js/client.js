/**
 * JavaScript for WebSockets client
 *
 * NB: There are lots of place where we use: wsState = wsSocketState()
 * This is because it's a good idea for code to always be working with the most
 * up to date value. We check the state regularly with startStateChecking(), but
 * that's mainly to update things even when we're doing nothing (eg, in case the
 * connection drops).
 */

const ws_ip = '10.0.150.150'
const ws_port = '8080'
const ws_route = 'ws'
const checkStateInterval = 500
const buttonStatePause = 1000
let connectBtn

let recvMsg = ''
let consoleEl
let terminal
// let checkIntervalID
let wsState = WebSocket.CLOSED
let prevWSstate = WebSocket.CLOSED

function clickBtn(btnEl, label) {
    const defLabel = btnEl.innerText
    btnEl.classList.add('pressed')
    btnEl.innerHTML = label
    setTimeout(() => {
        btnEl.innerHTML = defLabel
        btnEl.classList.remove('pressed')
    }, buttonStatePause)
}

// Callback for wsSocketConnect()
function receiveMsg(event) {
    console.log(event.data)
    // We're always expecting a JSON string. Let's turn it into an object
    recvMsg = JSON.parse(event.data)
    // Currently we're just printing the message to the terminal. But this
    // would also be the place to take action on received data/commands
    if (terminal && recvMsg) {
        if (Object.keys(recvMsg).length > 0) {
            for (const key in recvMsg) {
                terminal.print(`${key}: ${recvMsg[key]}`)
            }
        }
    }
}

function setConnectButton(state) {
    wsState = wsSocketState()
    switch (wsState) {
        case WebSocket.CONNECTING:
            connectBtn.classList.add('active')
            connectBtn.innerHTML = 'connecting'
            break
        case WebSocket.OPEN:
            connectBtn.classList.add('active')
            connectBtn.innerHTML = 'disconnect'
            break
        case WebSocket.CLOSING:
            connectBtn.classList.add('active')
            connectBtn.innerHTML = 'disconnecting'
            break
        case WebSocket.CLOSED:
            connectBtn.classList.remove('active')
            connectBtn.innerHTML = 'connect'
            break
    }
}

function startStateChecking() {
    const checkID = setInterval(() => {
        wsState = wsSocketState()
        if (wsState !== prevWSstate) {
            // State has changed
            prevWSstate = wsState   // reset
            switch (wsState) {
                case WebSocket.CONNECTING:
                    break
                case WebSocket.OPEN:
                    setConnectButton()
                    terminal.print('Connected')
                    break
                case WebSocket.CLOSING:
                case WebSocket.CLOSED:
                    setConnectButton()
                    terminal.print('Closed')
                    break
            }
        }
    }, checkStateInterval)
    return checkID // Not currently used - for future use
}

window.addEventListener('DOMContentLoaded', () => {
    connectBtn = document.getElementById('wsConnect')
    const statusBtn = document.getElementById('status')
    const sendBtn = document.getElementById('wsSend')
    const messageText = document.getElementById('wsSendMsg')
    consoleEl = document.getElementById('console')

    // Assign to outer variable
    terminal = new Console(consoleEl)

    connectBtn.addEventListener('click', () => {
        // Update wsState to make sure we're up to date
        wsState = wsSocketState()
        switch (wsState) {
            case WebSocket.CONNECTING:
                terminal.print('Connection in progress...')
                break
            case WebSocket.OPEN:
                // Currently connected, so disconnect
                terminal.print('Disconnecting... ')
                wsSocketDisconnect()
                break
            case WebSocket.CLOSING:
                terminal.print('Currently disconnecting...')
                break
            case WebSocket.CLOSED:
                terminal.print('Connecting... ')
                wsSocketConnect(receiveMsg, ws_ip, ws_port, ws_route)
                break
        }
        setTimeout(() => {
            if (wsSocketState() !== WebSocket.OPEN) {
                terminal.print('Not connected')
            }
        }, 5000)
    })

    sendBtn.addEventListener('click', () => {
        wsState = wsSocketState()
        if (wsState === WebSocket.OPEN) {
            clickBtn(sendBtn, 'sending')
            terminal.print('Sending: ')
            const msg = messageText.value
            terminal.print(msg + '\n')
            let sent = wsSocketSend(msg)
            if (sent) {
                terminal.print('Sent!')
            } else {
                terminal.print('Send failed!')
            }
        } else {
            terminal.print('No connection!')
        }
    })

    statusBtn.addEventListener('click', () => {
        wsState = wsSocketState()
        if (wsState === WebSocket.OPEN) {
            clickBtn(statusBtn, 'connecting')
		    terminal.print('Getting status... ')
            wsSocketSend('STATUS')
        } else {
            terminal.print('No connection!')
        }
    })

    startStateChecking()
})
