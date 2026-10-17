class Console {
    constructor(consoleElement, maxLines = 50) {
        this.maxLines = maxLines
        this.consoleElement = consoleElement
    }

    print(msgText) {
        // Create a line element
        const line = document.createElement('div')
        line.className = 'console-line'
        line.textContent = msgText // Safely handles special chars without innerHTML parsing

        this.consoleElement.appendChild(line)

        // Trim old nodes from the top if we exceed maxLines
        while (this.consoleElement.children.length > this.maxLines) {
            this.consoleElement.removeChild(this.consoleElement.firstElementChild)
        }

        // Auto-scroll to bottom
        this.consoleElement.scrollTop = this.consoleElement.scrollHeight
    }

    clear() {
        this.consoleElement.replaceChildren()
    }
}