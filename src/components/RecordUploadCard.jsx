import { useRef, useState } from 'react'
import { uploadRecordFile } from '../utils/api.js'

function DocumentIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="m3 7 9-4 9 4-9 4-9-4Z" /><path d="M3 7v10l9 4 9-4V7M12 11v10" /><path d="m7.5 5 9 4" /></svg>
}

export default function RecordUploadCard({ restaurantId, fieldKey, label, currentFile, onUploaded }) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  async function handleFileChange(fileList) {
    const file = fileList[0]
    if (!file) return
    setError('')
    setUploading(true)
    try {
      await uploadRecordFile(restaurantId, fieldKey, file)
      onUploaded(fieldKey, file.name)
    } catch (err) {
      setError(err.message || 'Upload failed. Please try again.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <article className="business-record-card">
      <div className="record-icon" aria-hidden="true"><DocumentIcon /></div>
      <div className="record-card-body">
        <h2>{label}</h2>
        <div className="upload-box">
          <span className={`file-name${currentFile ? ' chosen' : ''}`}>
            {uploading ? 'Uploading…' : currentFile || 'No file uploaded'}
          </span>
          <button type="button" className="btn-choose" disabled={uploading} onClick={() => inputRef.current?.click()}>
            {uploading ? '…' : currentFile ? 'Replace' : 'Upload'}
          </button>
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        <input
          type="file"
          accept=".csv"
          style={{ display: 'none' }}
          ref={inputRef}
          onChange={(e) => handleFileChange(e.target.files)}
        />
      </div>
    </article>
  )
}
