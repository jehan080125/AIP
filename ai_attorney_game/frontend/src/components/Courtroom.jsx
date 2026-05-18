import { useState, useEffect, useRef } from 'react';
import { useGameWebSocket } from '../hooks/useGameWebSocket';

export default function Courtroom() {
  const { isConnected, transcript, animationState, sendAction } = useGameWebSocket('ws://localhost:8000/ws/trial');
  
  const [inputText, setInputText] = useState('');
  const [selectedEvidence, setSelectedEvidence] = useState('');
  const scrollRef = useRef(null);
  
  // 시나리오의 증거물 하드코딩 (실제로는 서버에서 가져오도록 확장 가능)
  const inventory = [
    { id: 'ev_001', name: '부검 감정서' },
    { id: 'ev_002', name: '현장 CCTV 기록' },
    { id: 'ev_003', name: '가로등 정비 기록' }
  ];

  // 텍스트 창 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const handleSend = () => {
    if (!inputText.trim() && !selectedEvidence) return;
    
    const actionType = selectedEvidence ? 'present' : 'question';
    sendAction(actionType, selectedEvidence, inputText);
    
    setInputText('');
    setSelectedEvidence('');
  };

  return (
    <div className="w-full max-w-4xl h-[90vh] glass-panel flex flex-col overflow-hidden mx-auto p-6 gap-4 box-border">
      
      {/* 상단 헤더: 연결 상태 */}
      <div className="flex justify-between items-center text-sm font-semibold border-b border-[var(--border-color)] pb-3">
        <h1 className="text-xl tracking-wider text-[var(--text-main)]">⚖️ AI Attorney: First Turnabout</h1>
        <div className="flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-500'}`}></div>
          <span className="text-[var(--text-muted)]">{isConnected ? 'Server Connected' : 'Disconnected'}</span>
        </div>
      </div>

      {/* [상단 영역]: 피고인 상태 시각화 */}
      <div 
        className={`flex-1 min-h-[220px] bg-black/20 border border-[var(--border-color)] rounded-xl flex flex-col items-center justify-center transition-all duration-300
          ${animationState === 'breakdown' ? 'anim-breakdown' : ''}
          ${animationState === 'sweat' ? 'anim-shake' : ''}
        `}
      >
        <div className="w-24 h-24 bg-white/10 rounded-full flex items-center justify-center text-5xl mb-3 shadow-lg">
           {animationState === 'breakdown' ? '😱' : '🧑‍💼'}
        </div>
        <h2 className="text-2xl font-bold tracking-wide">김피고</h2>
        <span className={`px-3 py-1 rounded-full text-xs font-bold mt-2 uppercase tracking-widest ${
            animationState === 'breakdown' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400'
        }`}>
          {animationState === 'idle' ? 'Normal' : animationState}
        </span>
      </div>

      {/* [중단 영역]: 텍스트 트랜스크립트 */}
      <div 
        ref={scrollRef}
        className="h-[280px] bg-black/40 border border-[var(--border-color)] rounded-xl p-5 overflow-y-auto flex flex-col gap-4 scroll-smooth"
      >
        {transcript.map((msg) => (
          <div 
            key={msg.id} 
            className={`flex flex-col max-w-[85%] ${msg.speaker === 'player' ? 'self-end items-end' : 'self-start items-start'}`}
          >
            <span className="text-[10px] uppercase text-[var(--text-muted)] mb-1 font-bold">{msg.speaker}</span>
            <div 
              className={`p-3 rounded-2xl text-[15px] leading-relaxed shadow-md ${
                msg.speaker === 'player' 
                  ? 'bg-[var(--accent)] text-white rounded-br-none' 
                  : msg.speaker === 'system'
                  ? 'bg-transparent text-[var(--text-muted)] italic p-0 text-sm'
                  : 'bg-[var(--panel-bg)] text-[var(--text-main)] border border-[var(--border-color)] rounded-bl-none'
              }`}
            >
              {msg.text}
            </div>
          </div>
        ))}
      </div>

      {/* [하단 영역]: 컨트롤 패널 */}
      <div className="flex flex-col gap-3 pt-2">
        {/* 인벤토리 */}
        <div className="flex gap-3 items-center">
          <span className="text-sm font-semibold text-[var(--text-muted)] whitespace-nowrap">법정 기록:</span>
          <div className="flex flex-wrap gap-2">
            {inventory.map(ev => (
              <button
                key={ev.id}
                onClick={() => setSelectedEvidence(selectedEvidence === ev.id ? '' : ev.id)}
                className={`px-4 py-1.5 text-sm rounded-full border transition-all duration-200 ${
                  selectedEvidence === ev.id 
                    ? 'bg-yellow-500/20 border-yellow-500 text-yellow-300 shadow-[0_0_10px_rgba(234,179,8,0.3)]' 
                    : 'bg-transparent border-[var(--border-color)] text-[var(--text-muted)] hover:bg-white/10'
                }`}
              >
                {ev.name}
              </button>
            ))}
          </div>
        </div>
        
        {/* 입력 및 전송 */}
        <div className="flex gap-2">
          <input 
            type="text" 
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="심문할 내용이나 추궁할 포인트를 입력하세요..." 
            className="flex-1 bg-black/30 border border-[var(--border-color)] rounded-xl px-5 py-3 outline-none focus:border-[var(--accent)] text-[var(--text-main)] transition-colors"
          />
          <button 
            onClick={handleSend}
            disabled={!isConnected || (!inputText.trim() && !selectedEvidence)}
            className="bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:bg-gray-600 disabled:text-gray-400 disabled:cursor-not-allowed text-white font-black italic tracking-widest px-8 py-3 rounded-xl transition-all duration-200 transform active:scale-95 shadow-[0_0_15px_rgba(59,130,246,0.5)]"
          >
            OBJECTION!
          </button>
        </div>
      </div>

    </div>
  );
}
