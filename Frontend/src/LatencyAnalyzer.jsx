import React, { useState } from "react";
import axios from "axios";
import "./LatencyAnalyzer.css";

const API_BASE = "http://localhost:5000/api";

export default function LatencyAnalyzer() {
  const [file, setFile] = useState(null);
  const [timeFrom, setTimeFrom] = useState("2026-06-07 11:21:31");
  const [timeTo, setTimeTo] = useState("2026-06-11 17:00:00");
  const [timezone, setTimezone] = useState("Asia/Calcutta");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [messageType, setMessageType] = useState("info");
  const [downloadUrl, setDownloadUrl] = useState(null);
  const [reportContent, setReportContent] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [cidPreview, setCidPreview] = useState(null);

  const timezones = [
    "Asia/Calcutta",
    "UTC",
    "America/New_York",
    "Europe/London",
    "Asia/Tokyo",
    "Australia/Sydney"
  ];

  // Handle drag events
  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  // Handle file drop
  const handleDrop = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = e.dataTransfer.files;
    if (files && files[0]) {
      await processFile(files[0]);
    }
  };

  // Handle file input
  const handleFileChange = async (e) => {
    if (e.target.files && e.target.files[0]) {
      await processFile(e.target.files[0]);
    }
  };

  // Process file (validate and preview)
  const processFile = async (selectedFile) => {
    const allowedExtensions = [".csv", ".txt", ".xlsx", ".xls"];
    const fileExt = "." + selectedFile.name.split(".").pop().toLowerCase();

    if (!allowedExtensions.includes(fileExt)) {
      showMessage("Please upload a CSV, TXT, or XLSX file", "error");
      return;
    }

    setFile(selectedFile);
    console.log("✓ File selected:", selectedFile.name);

    // Try to extract and preview CIDs
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      console.log("Calling test-cid-extraction API...");
      const response = await axios.post(`${API_BASE}/test-cid-extraction`, formData);
      setCidPreview(response.data);
      showMessage(
        `✓ Found ${response.data.cids_found} conversation IDs in file`,
        "success"
      );
      console.log("✓ CID extraction successful:", response.data);
    } catch (error) {
      console.error("CID extraction error:", error);
      showMessage("Error reading file: " + (error.response?.data?.error || error.message), "error");
      setFile(null);
      setCidPreview(null);
    }
  };

  // Submit analysis
  const handleAnalyze = async (e) => {
    e.preventDefault();
    console.log("handleAnalyze called");
    console.log("File state:", file);
    console.log("timeFrom:", timeFrom, "timeTo:", timeTo);

    if (!file) {
      showMessage("Please upload a CSV file", "error");
      console.error("No file selected");
      return;
    }

    // Validate time format
    const timeRegex = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/;
    if (!timeRegex.test(timeFrom) || !timeRegex.test(timeTo)) {
      showMessage("Invalid date format. Use YYYY-MM-DD HH:MM:SS", "error");
      console.error("Date format invalid. timeFrom:", timeFrom, "timeTo:", timeTo);
      return;
    }

    console.log("✓ Validation passed, starting analysis...");
    setLoading(true);
    setMessage(null);
    setDownloadUrl(null);
    setReportContent(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("time_from", timeFrom);
    formData.append("time_to", timeTo);
    formData.append("timezone", timezone);

    try {
      console.log("Sending request to:", `${API_BASE}/analyze`);
      const response = await axios.post(`${API_BASE}/analyze`, formData, {
        headers: { "Content-Type": "multipart/form-data" }
      });

      console.log("✓ Analysis response:", response.data);
      setDownloadUrl(response.data.download_url);
      setReportContent(response.data.report_content);
      showMessage(
        `✓ Analysis complete! Processed ${response.data.cids_processed} conversations.`,
        "success"
      );
    } catch (error) {
      console.error("Analysis error:", error);
      console.error("Error response:", error.response?.data);
      showMessage(
        "Analysis failed: " + (error.response?.data?.error || error.message),
        "error"
      );
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (text, type) => {
    setMessage(text);
    setMessageType(type);
    setTimeout(() => setMessage(null), 5000);
  };

  const downloadReport = () => {
    if (downloadUrl) {
      // Remove /api prefix if it exists to avoid double /api/api
      const cleanUrl = downloadUrl.replace(/^\/api/, '');
      const fullUrl = `${API_BASE}${cleanUrl}`;
      const filename = downloadUrl.split("/").pop();

      // Create and trigger download
      const link = document.createElement("a");
      link.href = fullUrl;
      link.download = filename; // Forces download instead of opening in browser
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      showMessage(`✓ Downloading ${filename}...`, "success");
    } else {
      showMessage("No report available to download", "error");
    }
  };

  return (
    <div className="analyzer-container">
      <div className="analyzer-card">
        {/* Header */}
        <div className="header">
          <h1>Latency Analysis Tool</h1>
          <p className="subtitle">Analyze conversation latencies with ease</p>
        </div>

        {/* Message */}
        {message && (
          <div className={`message message-${messageType}`}>
            {message}
          </div>
        )}

        {/* File Upload Section */}
        <div className="section">
          <h2 className="section-title">1. Upload Conversation IDs</h2>
          <div
            className={`drag-drop ${dragActive ? "active" : ""} ${file ? "has-file" : ""}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            <input
              type="file"
              accept=".csv,.txt,.xlsx,.xls"
              onChange={handleFileChange}
              id="file-input"
              style={{ display: "none" }}
            />
            <label htmlFor="file-input" className="drag-drop-label">
              {file ? (
                <>
                  <span className="file-icon">✓</span>
                  <p className="file-name">{file.name}</p>
                  {cidPreview && (
                    <p className="file-info">
                      Found {cidPreview.cids_found} conversation IDs
                    </p>
                  )}
                </>
              ) : (
                <>
                  <span className="upload-icon">📁</span>
                  <p>Drag & drop your CSV, TXT, or XLSX file here</p>
                  <p className="file-formats">CSV • TXT • XLSX</p>
                  <p className="or-text">or</p>
                  <button type="button" className="browse-btn">
                    Browse Files
                  </button>
                </>
              )}
            </label>
          </div>
        </div>

        {/* Time Window Section */}
        <div className="section">
          <h2 className="section-title">2. Set Time Window</h2>
          <div className="time-inputs">
            <div className="time-group">
              <label>From (IST)</label>
              <input
                type="text"
                value={timeFrom}
                onChange={(e) => setTimeFrom(e.target.value)}
                placeholder="YYYY-MM-DD HH:MM:SS"
              />
            </div>
            <div className="time-group">
              <label>To (IST)</label>
              <input
                type="text"
                value={timeTo}
                onChange={(e) => setTimeTo(e.target.value)}
                placeholder="YYYY-MM-DD HH:MM:SS"
              />
            </div>
            <div className="time-group">
              <label>Timezone</label>
              <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
                {timezones.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Action Section */}
        <div className="section">
          <button
            onClick={handleAnalyze}
            disabled={!file || loading}
            className={`analyze-btn ${loading ? "loading" : ""}`}
          >
            {loading ? (
              <>
                <span className="spinner"></span>
                Analyzing...
              </>
            ) : (
              <>
                <span>🚀</span>
                Run Analysis
              </>
            )}
          </button>
        </div>

        {/* Report Section */}
        {reportContent && (
          <div className="section report-section">
            <h2 className="section-title">✓ Analysis Report</h2>
            <div className="report-display">
              <pre className="report-content">{reportContent}</pre>
            </div>
            <button onClick={downloadReport} className="download-btn">
              <span>📥</span>
              Download Report
            </button>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="footer">
        <p>Upload a CSV with conversation IDs • Set your time window • Run analysis • Download results</p>
      </div>
    </div>
  );
}
