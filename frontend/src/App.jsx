import React, { useState, useRef } from 'react';
import { Upload, FileText, Download, AlertCircle, CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

function App() {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);
    const fileInputRef = useRef(null);

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

    const generatePaper = async () => {
        if (!file) return;

        setLoading(true);
        setError(null);
        setSuccess(false);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/generate-paper', {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to generate paper');
            }

            // Handle file download
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Exam_Paper_${new Date().toISOString().slice(0, 10)}.docx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            setSuccess(true);
            setFile(null);
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

            <div className="container">
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                >
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '20px' }}>
                        <Sparkles className="text-primary" size={48} color="#8b5cf6" />
                    </div>
                    <h1>Symphony</h1>
                    <p className="subtitle">Upload your plotting sheet to generate a question paper in seconds.</p>
                </motion.div>

                <motion.div
                    className="glass upload-zone"
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    onClick={() => fileInputRef.current.click()}
                    onDragOver={handleDragOver}
                    onDrop={handleDrop}
                    animate={{ borderColor: file ? '#8b5cf6' : 'rgba(255, 255, 255, 0.1)' }}
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

                <AnimatePresence>
                    {error && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            className="status status-error"
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
                        >
                            <CheckCircle2 size={20} />
                            <span>Paper generated and downloaded successfully!</span>
                        </motion.div>
                    )}
                </AnimatePresence>

                <motion.button
                    className="btn"
                    disabled={!file || loading}
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
                    {loading ? 'Processing...' : 'Generate Word Document'}
                </motion.button>
            </div>
        </>
    );
}

export default App;
