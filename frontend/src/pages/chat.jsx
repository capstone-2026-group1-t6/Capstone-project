import { useEffect, useRef, useState } from "react"

const suggestions = [
  "What can I ask you to do?",
  "Which one of my projects is performing the best?",
  "What projects should I be concerned about right now?",
]

function SparkleHeading() {
  return (
    <div className="flex flex-col items-center gap-8 text-center">
      <svg
        width="37"
        height="38"
        viewBox="186 0 37 38"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="h-9 w-9"
      >
        <path
          d="M197 16.8281C197 16.8281 197.579 22.2355 199.836 24.4921C202.093 26.7487 207.5 27.3281 207.5 27.3281C207.5 27.3281 202.093 27.9074 199.836 30.164C197.579 32.4206 197 37.8281 197 37.8281C197 37.8281 196.421 32.4206 194.164 30.164C191.907 27.9074 186.5 27.3281 186.5 27.3281C186.5 27.3281 191.907 26.7487 194.164 24.4921C196.421 22.2355 197 16.8281 197 16.8281Z"
          fill="#160211"
        />
        <path
          d="M212 7.91403C212 7.91403 212.579 13.3215 214.836 15.5781C217.093 17.8347 222.5 18.414 222.5 18.414C222.5 18.414 217.093 18.9934 214.836 21.25C212.579 23.5066 212 28.914 212 28.914C212 28.914 211.421 23.5066 209.164 21.25C206.907 18.9934 201.5 18.414 201.5 18.414C201.5 18.414 206.907 17.8347 209.164 15.5781C211.421 13.3215 212 7.91403 212 7.91403Z"
          fill="#160211"
        />
        <path
          d="M197 0C197 0 197.579 5.40743 199.836 7.66405C202.093 9.92066 207.5 10.5 207.5 10.5C207.5 10.5 202.093 11.0793 199.836 13.336C197.579 15.5926 197 21 197 21C197 21 196.421 15.5926 194.164 13.336C191.907 11.0793 186.5 10.5 186.5 10.5C186.5 10.5 191.907 9.92066 194.164 7.66405C196.421 5.40743 197 0 197 0Z"
          fill="#160211"
        />
      </svg>
      <h1 className="font-sans text-2xl font-normal text-gray-900">
        Ask our AI anything
      </h1>
    </div>
  )
}

export default function Chat() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [isThinking, setIsThinking] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    if (messages.length > 0) {
      scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [messages]);

  const sendMessage = (text) => {
    const trimmed = text.trim()
    if (!trimmed) return

    const userMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content: trimmed,
    }
    setMessages((prev) => [...prev, userMessage])
    setInput("")
    setIsThinking(true)

    setTimeout(() => {
      setIsThinking(false)
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          content:
            "say meaow to get your answer",
        },
      ])
    }, 1100)
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    sendMessage(input)
  }

  const hasMessages = messages.length > 0

  return (
    <div className="relative flex flex-1 min-h-0 flex-col overflow-hidden bg-white">
      {/* Background blurs */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/3 h-[420px] w-[420px] -translate-x-1/4 -translate-y-1/2 rounded-full bg-blue-400/50 blur-[130px]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-2/3 h-[380px] w-[380px] -translate-x-3/4 rounded-full bg-pink-400/50 blur-[150px]"
      />

      <div className="relative z-10 flex flex-1 min-h-0 flex-col">
        {!hasMessages ? (
          // Empty state with suggestions
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center gap-12 px-4 py-16">
            <SparkleHeading />

            <div className="flex w-full flex-col items-center gap-4">
              <p className="font-sans text-sm font-bold text-gray-600">
                Suggestions on what to ask Our AI
              </p>
              <div className="flex w-full flex-col flex-wrap items-stretch justify-center gap-3 sm:flex-row sm:items-start">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => sendMessage(suggestion)}
                    className="flex min-h-[38px] flex-1 items-center justify-center rounded-lg border border-white bg-white/50 px-4 py-2.5 text-center font-body text-sm text-gray-900 shadow-sm backdrop-blur transition-colors hover:bg-white/80 sm:min-w-[200px]"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          // Messages view
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 overflow-y-auto px-4 py-8">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex w-full ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 font-body text-sm leading-relaxed sm:max-w-[75%] ${
                    message.role === "user"
                      ? "bg-gray-900 text-white"
                      : "border border-gray-200 bg-white/80 text-gray-900 shadow-sm backdrop-blur"
                  }`}
                >
                  {message.content}
                </div>
              </div>
            ))}
            {isThinking && (
              <div className="flex justify-start">
                <div className="flex items-center gap-1.5 rounded-2xl border border-gray-200 bg-white/80 px-4 py-3 shadow-sm backdrop-blur">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400" />
                </div>
              </div>
            )}
            <div ref={scrollRef} />
          </div>
        )}

        {/* Input form */}
        <form
          onSubmit={handleSubmit}
          className="sticky bottom-0 z-10 mx-auto flex w-full max-w-3xl items-center gap-2 bg-white/90 px-4 pb-8 pt-4 backdrop-blur-md"
        >
          <div className="flex h-14 w-full items-center justify-between gap-3 rounded-lg border border-gray-300 bg-white px-4">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask me anything about your projects"
              className="w-full bg-transparent font-sans text-sm text-gray-900 placeholder:text-gray-600 focus:outline-none"
            />
            <button
              type="submit"
              aria-label="Send message"
              className="flex shrink-0 items-center justify-center transition-opacity hover:opacity-70 disabled:opacity-40"
              disabled={!input.trim()}
            >
              <svg
                width="36"
                height="36"
                viewBox="0 0 36 36"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <g clipPath="url(#clip0_chat_send)">
                  <path
                    d="M34.8522 17.4802L1.24281 0.629307C1.1062 0.561003 0.949507 0.544932 0.800846 0.581093C0.635855 0.621881 0.493748 0.726385 0.405641 0.871724C0.317535 1.01706 0.290608 1.19139 0.330757 1.35654L3.79415 15.5074C3.84638 15.7204 4.00308 15.8931 4.21201 15.9614L10.1464 17.9985L4.21602 20.0356C4.0071 20.1079 3.8504 20.2766 3.80219 20.4896L0.330757 34.6606C0.294596 34.8092 0.310668 34.9659 0.378971 35.0985C0.535668 35.4159 0.921382 35.5445 1.24281 35.3878L34.8522 18.6333C34.9767 18.5731 35.0772 18.4686 35.1415 18.3481C35.2982 18.0266 35.1696 17.6409 34.8522 17.4802ZM4.29236 30.6347L6.31335 22.3739L18.1741 18.3039C18.2665 18.2717 18.3428 18.1994 18.375 18.103C18.4312 17.9342 18.3428 17.7534 18.1741 17.6931L6.31335 13.6271L4.3004 5.3985L29.5325 18.0507L4.29236 30.6347Z"
                    fill="#456288"
                    fillOpacity={input.trim() ? "1" : "0.5"}
                  />
                </g>
                <defs>
                  <clipPath id="clip0_chat_send">
                    <rect width="36" height="36" fill="white" />
                  </clipPath>
                </defs>
              </svg>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}