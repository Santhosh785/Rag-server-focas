import React, { useState, useRef } from 'react';
import { Upload, FileText, Download, AlertCircle, CheckCircle2, Loader2, GraduationCap, Plus, Trash2, LayoutList, Dices } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
    const [mode, setMode] = useState('upload'); // 'upload' or 'manual'
    
    // Upload Mode State
    const [file, setFile] = useState(null);
    const fileInputRef = useRef(null);

    // Manual Mode State
    const [globalLevel, setGlobalLevel] = useState('Intermediate');
    const [globalSubject, setGlobalSubject] = useState('FM');
    const [availableChapters, setAvailableChapters] = useState([]);
    const [loadingChapters, setLoadingChapters] = useState(false);
    const [questions, setQuestions] = useState([
        { chapter_number: '', unit: '', question_number: '', marks: ''}
    ]);

    // Random Mode State
    const [randomLevel, setRandomLevel] = useState('Intermediate');
    const [randomSubject, setRandomSubject] = useState('FM');
    const [randomChapter, setRandomChapter] = useState('');
    const [randomMarks, setRandomMarks] = useState(50);

    // Shared State
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    // --- Upload Mode Handlers ---
    const handleDragOver = (e) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const droppedFile = e.dataTransfer.files[0];
        if (droppedFile && droppedFile.name.match(/\.(xlsx|xls)$/)) {
            setFile(droppedFile);
            setError(null);
        } else {
            setError("Please upload a valid Excel file (.xlsx or .xls)");
        }
    };

    const handleFileSelect = (e) => {
        const selectedFile = e.target.files[0];
        if (selectedFile) {
            setFile(selectedFile);
            setError(null);
        }
    };

    // --- Manual Mode Handlers ---
    const updateQuestion = (index, field, value) => {
        const newQs = [...questions];
        newQs[index][field] = value;
        setQuestions(newQs);
        setError(null);
    };

    const addQuestion = () => {
        const lastQ = questions[questions.length - 1];
        setQuestions([...questions, { 
            chapter_number: lastQ ? lastQ.chapter_number : '', 
            unit: lastQ ? lastQ.unit : '', 
            question_number: '', 
            marks: lastQ ? lastQ.marks : '' 
        }]);
    };

    const removeQuestion = (index) => {
        if (questions.length === 1) return;
        setQuestions(questions.filter((_, i) => i !== index));
    };

    // Fetch chapters when subject changes
    const fetchChapters = async (subject) => {
        if (!subject) return;
        setLoadingChapters(true);
        try {
            const API_URL = import.meta.env.VITE_API_URL || '';
            const response = await fetch(`${API_URL}/api/chapters/${subject}`);
            if (response.ok) {
                const data = await response.json();
                setAvailableChapters(data.chapters || []);
            } else {
                setAvailableChapters([]);
            }
        } catch (err) {
            console.error('Error fetching chapters:', err);
            setAvailableChapters([]);
        } finally {
            setLoadingChapters(false);
        }
    };

    // Fetch chapters when globalSubject changes in manual mode or randomSubject in random mode
    React.useEffect(() => {
        if (mode === 'manual' && globalSubject) {
            fetchChapters(globalSubject);
        } else if (mode === 'random' && randomSubject) {
            fetchChapters(randomSubject);
        }
    }, [globalSubject, randomSubject, mode]);

    // --- Submit Handler ---
    const generatePaper = async () => {
        if (mode === 'upload' && !file) return;
        if (mode === 'manual' && questions.length === 0) return;

        setLoading(true);
        setError(null);
        setSuccess(false);

        try {
            let response;
            
            const API_URL = import.meta.env.VITE_API_URL || '';

            if (mode === 'upload') {
                const formData = new FormData();
                formData.append('file', file);
                response = await fetch(`${API_URL}/api/generate-paper`, {
                    method: 'POST',
                    body: formData,
                });
            } else if (mode === 'manual') {
                // Manual Mode Validation
                if (!globalLevel || !globalSubject) {
                    throw new Error("Please provide the Exam Level and Subject.");
                }

                for (let i = 0; i < questions.length; i++) {
                    const q = questions[i];
                    if (!q.chapter_number || !q.question_number) {
                        throw new Error(`Row ${i + 1} is missing a Chapter or Question Number.`);
                    }
                }
                
                const payload = questions.map(q => ({
                    level: globalLevel,
                    subject: globalSubject,
                    chapter_number: String(q.chapter_number),
                    unit: String(q.unit || ""),
                    question_number: String(q.question_number),
                    marks: String(q.marks || "")
                }));
                
                response = await fetch(`${API_URL}/api/generate-paper-json`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ questions: payload }),
                });
            } else if (mode === 'random') {
                if (!randomLevel || !randomSubject) {
                    throw new Error("Please provide the Exam Level and Subject.");
                }
                const payload = {
                    level: randomLevel,
                    subject: randomSubject,
                    chapter_number: randomChapter,
                    total_marks: parseInt(randomMarks, 10)
                };
                response = await fetch(`${API_URL}/api/generate-random-paper`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Failed to generate paper');
            }

            // Handle file download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `FOCAS_Exam_Package_${new Date().toISOString().slice(0, 10)}.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            setSuccess(true);
            if (mode === 'upload') setFile(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <div className="bg-gradient" />
            <div className="bg-blobs">
                <div className="blob blob-1" />
                <div className="blob blob-2" />
                <div className="blob blob-3" />
            </div>

            <div className="container" style={{ maxWidth: mode === 'manual' ? '900px' : '600px', transition: 'max-width 0.4s ease' }}>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                >
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '20px' }}>
                        <GraduationCap className="text-primary" size={48} color="#3b82f6" />
                    </div>
                    <h1 style={{fontSize: '2.5rem'}}>FOCAS Exam Generator</h1>
                    <p className="subtitle">Your Last Attempt — High-quality, precise question papers in seconds.</p>
                </motion.div>

                {/* --- Tab Selector --- */}
                <div style={{ display: 'flex', justifyContent: 'center', gap: '20px', marginBottom: '30px', flexWrap: 'wrap' }}>
                    <button 
                        className={`tab-btn ${mode === 'upload' ? 'active' : ''}`}
                        onClick={() => { setMode('upload'); setError(null); setSuccess(false); }}
                        style={{ background: mode === 'upload' ? 'rgba(59, 130, 246, 0.2)' : 'transparent', border: '1px solid #3b82f6', padding: '10px 20px', borderRadius: '12px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <Upload size={18} /> Upload Excel
                    </button>
                    <button 
                        className={`tab-btn ${mode === 'manual' ? 'active' : ''}`}
                        onClick={() => { setMode('manual'); setError(null); setSuccess(false); }}
                        style={{ background: mode === 'manual' ? 'rgba(59, 130, 246, 0.2)' : 'transparent', border: '1px solid #3b82f6', padding: '10px 20px', borderRadius: '12px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <LayoutList size={18} /> Manual Builder
                    </button>
                    <button 
                        className={`tab-btn ${mode === 'random' ? 'active' : ''}`}
                        onClick={() => { setMode('random'); setError(null); setSuccess(false); }}
                        style={{ background: mode === 'random' ? 'rgba(59, 130, 246, 0.2)' : 'transparent', border: '1px solid #3b82f6', padding: '10px 20px', borderRadius: '12px', color: 'white', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px' }}
                    >
                        <Dices size={18} /> Random Generator
                    </button>
                </div>

                {/* --- Upload Mode UI --- */}
                {mode === 'upload' && (
                    <motion.div
                        className="glass upload-zone"
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.99 }}
                        onClick={() => fileInputRef.current.click()}
                        onDragOver={handleDragOver}
                        onDrop={handleDrop}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1, borderColor: file ? '#3b82f6' : 'rgba(255, 255, 255, 0.1)' }}
                    >
                        <input
                            type="file"
                            ref={fileInputRef}
                            onChange={handleFileSelect}
                            style={{ display: 'none' }}
                            accept=".xlsx, .xls"
                        />

                        <div className="upload-icon-container" style={{ display: 'flex', justifyContent: 'center' }}>
                            {file ? (
                                <FileText size={64} className="upload-icon" />
                            ) : (
                                <Upload size={64} className="upload-icon" />
                            )}
                        </div>

                        <p className="upload-text">
                            {file ? file.name : 'Click or drag & drop plotting sheet'}
                        </p>
                        <p className="upload-hint">Excel files only (must contain level, subject, chapter, and question number)</p>
                    </motion.div>
                )}

                {/* --- Manual Mode UI --- */}
                {mode === 'manual' && (
                    <motion.div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        
                        {/* Global Config Card */}
                        <div className="glass" style={{ padding: '24px', display: 'flex', gap: '30px', alignItems: 'center' }}>
                            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left' }}>
                                <label style={{ fontSize: '0.9rem', color: '#93c5fd', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Exam Level</label>
                                <select className="builder-input" value={globalLevel} onChange={(e) => setGlobalLevel(e.target.value)} style={{ padding: '12px', borderRadius: '10px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s', width: '100%'}}>
                                    <option value="Foundation">Foundation</option>
                                    <option value="Intermediate">Intermediate</option>
                                    <option value="Final">Final</option>
                                </select>
                            </div>
                            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px', textAlign: 'left' }}>
                                <label style={{ fontSize: '0.9rem', color: '#93c5fd', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Subject</label>
                                <input className="builder-input" type="text" placeholder="e.g. FM" value={globalSubject} onChange={(e) => setGlobalSubject(e.target.value)} style={{ padding: '12px', borderRadius: '10px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s', width: '100%'}} />
                            </div>
                        </div>

                        {/* Questions List Card */}
                        <div className="glass" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                <h3 style={{ margin: 0, fontSize: '1.2rem', color: '#fff' }}>Questions</h3>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1.5fr 1fr 1fr 40px', gap: '16px', padding: '0 10px' }}>
                                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Chapter</div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Unit (Optional)</div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Q Num</div>
                                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase' }}>Marks</div>
                                <div></div>
                            </div>

                            <AnimatePresence>
                                {questions.map((q, idx) => (
                                    <motion.div 
                                        key={idx} 
                                        initial={{ opacity: 0, height: 0 }} 
                                        animate={{ opacity: 1, height: 'auto' }} 
                                        exit={{ opacity: 0, height: 0 }}
                                        style={{ display: 'grid', gridTemplateColumns: '1.5fr 1.5fr 1fr 1fr 40px', gap: '16px', alignItems: 'center', background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}
                                    >
                                        <select
                                            className="builder-input"
                                            value={q.chapter_number}
                                            onChange={(e) => updateQuestion(idx, 'chapter_number', e.target.value)}
                                            style={{ padding: '12px', borderRadius: '8px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid transparent', transition: 'all 0.2s', width: '100%'}}
                                            disabled={loadingChapters || availableChapters.length === 0}
                                        >
                                            <option value="">Select Chapter...</option>
                                            {availableChapters.map(ch => (
                                                <option key={ch.number} value={ch.number}>
                                                    {ch.display}
                                                </option>
                                            ))}
                                        </select>
                                        <input className="builder-input" type="text" placeholder="blank if no unit" value={q.unit} onChange={(e) => updateQuestion(idx, 'unit', e.target.value)} style={{ padding: '12px', borderRadius: '8px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid transparent', transition: 'all 0.2s', width: '100%'}} />
                                        <input className="builder-input" type="text" placeholder="Q1" value={q.question_number} onChange={(e) => updateQuestion(idx, 'question_number', e.target.value)} style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', color: 'white', border: '1px solid rgba(59, 130, 246, 0.3)', transition: 'all 0.2s', width: '100%'}} />
                                        <input className="builder-input" type="text" placeholder="5" value={q.marks} onChange={(e) => updateQuestion(idx, 'marks', e.target.value)} style={{ padding: '12px', borderRadius: '8px', background: 'rgba(59, 130, 246, 0.1)', color: 'white', border: '1px solid rgba(59, 130, 246, 0.3)', transition: 'all 0.2s', width: '100%'}} />
                                        
                                        <button 
                                            onClick={() => removeQuestion(idx)} 
                                            disabled={questions.length === 1} 
                                            style={{ background: 'transparent', border: 'none', color: questions.length === 1 ? 'rgba(255,255,255,0.1)' : '#ef4444', cursor: questions.length === 1 ? 'not-allowed' : 'pointer', display: 'flex', justifyContent: 'center' }}
                                        >
                                            <Trash2 size={20} />
                                        </button>
                                    </motion.div>
                                ))}
                            </AnimatePresence>

                            <button 
                                onClick={addQuestion} 
                                style={{ marginTop: '10px', background: 'rgba(59, 130, 246, 0.15)', border: '1px dashed rgba(59, 130, 246, 0.5)', color: '#93c5fd', padding: '16px', borderRadius: '12px', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', fontWeight: 500, transition: 'all 0.2s' }}
                                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(59, 130, 246, 0.25)'; }}
                                onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(59, 130, 246, 0.15)'; }}
                            >
                                <Plus size={20} /> Add Another Question
                            </button>
                        </div>
                    </motion.div>
                )}

                {/* --- Random Mode UI --- */}
                {mode === 'random' && (
                    <motion.div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                        <div className="glass" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', textAlign: 'left' }}>
                            <h3 style={{ margin: 0, fontSize: '1.2rem', color: '#fff', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '12px' }}>Auto-Generate Random Paper</h3>
                            
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <label style={{ fontSize: '0.9rem', color: '#93c5fd', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Exam Level</label>
                                    <select className="builder-input" value={randomLevel} onChange={(e) => setRandomLevel(e.target.value)} style={{ padding: '12px', borderRadius: '10px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s', width: '100%'}}>
                                        <option value="Foundation">Foundation</option>
                                        <option value="Intermediate">Intermediate</option>
                                        <option value="Final">Final</option>
                                    </select>
                                </div>
                                
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <label style={{ fontSize: '0.9rem', color: '#93c5fd', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Subject</label>
                                    <input className="builder-input" type="text" placeholder="e.g. FM" value={randomSubject} onChange={(e) => setRandomSubject(e.target.value)} style={{ padding: '12px', borderRadius: '10px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s', width: '100%'}} />
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '20px' }}>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Chapter Filter (Optional)</label>
                                    <select
                                        className="builder-input"
                                        value={randomChapter}
                                        onChange={(e) => setRandomChapter(e.target.value)}
                                        style={{ padding: '12px', borderRadius: '10px', background: 'rgba(0,0,0,0.2)', color: 'white', border: '1px solid rgba(255,255,255,0.1)', transition: 'all 0.2s', width: '100%'}}
                                        disabled={loadingChapters}
                                    >
                                        <option value="">All Chapters (Full book mix)</option>
                                        {availableChapters.map(ch => (
                                            <option key={ch.number} value={ch.number}>
                                                {ch.display}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    <label style={{ fontSize: '0.9rem', color: '#3b82f6', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Target Marks</label>
                                    <select className="builder-input" value={randomMarks} onChange={(e) => setRandomMarks(e.target.value)} style={{ padding: '12px', borderRadius: '10px', background: 'rgba(59, 130, 246, 0.1)', color: 'white', border: '1px solid rgba(59, 130, 246, 0.4)', transition: 'all 0.2s', width: '100%'}}>
                                        <option value="25">25 Marks</option>
                                        <option value="50">50 Marks (Approx)</option>
                                        <option value="75">75 Marks (Approx)</option>
                                        <option value="100">100 Marks (Full Test)</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}

                <AnimatePresence>
                    {error && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="status status-error"
                            style={{marginTop: '20px'}}
                        >
                            <AlertCircle size={20} />
                            <span>{error}</span>
                        </motion.div>
                    )}

                    {success && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="status status-success"
                            style={{marginTop: '20px'}}
                        >
                            <CheckCircle2 size={20} />
                            <span>Exam package (Paper + Answers) generated and downloaded!</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                <motion.button
                    className="btn"
                    style={{ marginTop: '20px' }}
                    disabled={(mode === 'upload' && !file) || loading}
                    onClick={(e) => {
                        e.stopPropagation();
                        generatePaper();
                    }}
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                >
                    {loading ? (
                        <Loader2 className="spinner" />
                    ) : (
                        <Download size={20} />
                    )}
                    {loading ? 'Processing...' : 'Generate Exam Package (ZIP)'}
                </motion.button>
            </div>

            <style>{`
                .builder-input:focus {
                    outline: 2px solid #3b82f6;
                }
                option {
                    background: #1e1e2f;
                    color: white;
                }
            `}</style>
        </>
    );
}

export default App;
