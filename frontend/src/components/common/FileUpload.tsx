/** Drag-and-drop file upload component. */

import { useRef, useState, useCallback } from 'react';

interface FileUploadProps {
  onFileSelect: (file: File) => void;
  accept?: string;
  maxSizeMB?: number;
  disabled?: boolean;
  label?: string;
}

export function FileUpload({
  onFileSelect,
  accept = '.pdf,.png,.jpg,.jpeg,.tiff,.tif',
  maxSizeMB = 20,
  disabled = false,
  label = 'Drop a file here or click to browse',
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((file: File) => {
    setError(null);
    if (file.size > maxSizeMB * 1024 * 1024) {
      setError(`File exceeds ${maxSizeMB} MB limit`);
      return;
    }
    onFileSelect(file);
  }, [onFileSelect, maxSizeMB]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [disabled, handleFile]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!disabled) setDragOver(true);
  }, [disabled]);

  const onDragLeave = useCallback(() => setDragOver(false), []);

  const onChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    // Reset input so same file can be re-selected
    e.target.value = '';
  }, [handleFile]);

  return (
    <div
      className={`file-upload-zone ${dragOver ? 'file-upload-dragover' : ''} ${disabled ? 'file-upload-disabled' : ''}`}
      onDrop={onDrop}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        onChange={onChange}
        style={{ display: 'none' }}
        disabled={disabled}
      />
      <div className="file-upload-icon">+</div>
      <p className="file-upload-label">{label}</p>
      <p className="file-upload-hint">PDF, PNG, JPG, TIFF — max {maxSizeMB} MB</p>
      {error && <p className="file-upload-error">{error}</p>}
    </div>
  );
}
