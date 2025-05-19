// scripts.js - JS logic for the alternative frontend of VideoUnderstanding

document.addEventListener('DOMContentLoaded', function () {
  const fileInput = document.getElementById('fileInput');
  const uploadArea = document.getElementById('uploadArea');
  const filename = document.getElementById('filename');
  const submitBtn = document.getElementById('submitBtn');
  const progress = document.getElementById('progress');
  const progressBar = document.getElementById('progressBar');
  const result = document.getElementById('result');
  const uploadText = document.getElementById('uploadText');
  const videoPreview = document.getElementById('videoPreview');
  const langSelect = document.getElementById('lang');
  const ttsVoiceSelect = document.getElementById('tts_voice');

  // Drag & drop
  uploadArea.addEventListener('click', (e) => {
    // Prevent double opening if the click comes from the file input
    if (e.target === fileInput) return;
    // Only trigger click if the input has no files selected
    if (!fileInput.files.length) fileInput.click();
  });
  // Prevent double opening of the file selector
  fileInput.addEventListener('click', (e) => {
    e.stopPropagation();
  });
  uploadArea.addEventListener('dragover', e => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
  });
  uploadArea.addEventListener('dragleave', e => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
  });
  uploadArea.addEventListener('drop', e => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      updateFilename();
      showVideoPreview();
    }
  });
  fileInput.addEventListener('change', () => {
    updateFilename();
    showVideoPreview();
    // Do not clear the input value here, only after successful submit
  });
  function updateFilename() {
    if (fileInput.files.length) {
      filename.textContent = fileInput.files[0].name;
      submitBtn.disabled = false;
      uploadText.style.display = 'none';
    } else {
      filename.textContent = '';
      submitBtn.disabled = true;
      uploadText.style.display = '';
      videoPreview.style.display = 'none';
    }
  }
  function showVideoPreview() {
    if (fileInput.files.length) {
      const file = fileInput.files[0];
      if (file.type.startsWith('video/')) {
        const url = URL.createObjectURL(file);
        videoPreview.src = url;
        videoPreview.style.display = 'block';
      } else {
        videoPreview.style.display = 'none';
      }
    } else {
      videoPreview.style.display = 'none';
    }
  }
  // Status message area
  const statusMsg = document.createElement('div');
  statusMsg.id = 'statusMsg';
  statusMsg.className = 'status-msg'; // Use class for CSS styles
  // Inline styles removed, handled by CSS
  
  // Insert the status message and the new progress bar into the DOM
  const form = document.getElementById('uploadForm');
  form.appendChild(statusMsg); // Add at the end of the form
  const stepProgressBar = document.getElementById('stepProgressBar'); // Get the new progress bar

  function setStatus(msg) {
    statusMsg.textContent = msg;
  }
  function clearStatus() {
    statusMsg.textContent = '';
  }

  // --- Step progress bar ---
  // Step names are now taken from the HTML

  // The step progress bar is already in the HTML, no need to create it here.

  function setStepActive(idx) {
    const stepsIds = ['step-upload', 'step-extract', 'step-analyze', 'step-tts', 'step-assemble'];
    stepsIds.forEach((stepId, i) => {
      const el = document.getElementById(stepId);
      if (el) {
        el.classList.remove('active', 'done', 'future'); // Clear previous classes
        if (i === idx) {
          el.classList.add('active');
        } else if (i < idx) {
          el.classList.add('done');
        } else {
          el.classList.add('future');
        }
      }
    });
    // Text styling (bold, underline) is handled via CSS for .step.active
  }

  // Form submit
  document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) return;
    submitBtn.disabled = true;
    if(stepProgressBar) stepProgressBar.style.display = 'flex'; // Show the progress bar
    result.innerHTML = '';
    
    // Sync setStatus and setStepActive
    setStatus('Uploading video...');
    setStepActive(0);
    
    let video_id = null, filename_server = null, frames = null, descriptions = null, audio_chunks = null, video_b64 = null;
    let usedVoice = ttsVoiceSelect.value;
    let usedLang = langSelect.value;
    try {
      // 1. Upload video
      const uploadData = new FormData();
      uploadData.append('file', fileInput.files[0]);
      const uploadRes = await fetch('/upload-video', { method: 'POST', body: uploadData });
      if (!uploadRes.ok) throw new Error('Error uploading the video');
      const uploadJson = await uploadRes.json();
      video_id = uploadJson.video_id;
      filename_server = uploadJson.filename; // Renamed to avoid conflict with the global filename variable
      
      setStatus('Extracting frames...');
      setStepActive(1); // Update step BEFORE the call

      // 2. Extract frames
      const extractRes = await fetch('/extract-frames', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id, filename: filename_server })
      });
      if (!extractRes.ok) throw new Error('Error extracting frames');
      const extractJson = await extractRes.json();
      frames = extractJson.frames;
      
      setStatus('Analyzing video...');
      setStepActive(2); // Update step BEFORE the call

      // 3. Analyze frames
      const analyzeRes = await fetch('/analyze-frames', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id, frames, lang: langSelect.value })
      });
      if (!analyzeRes.ok) throw new Error('Error analyzing frames');
      const analyzeJson = await analyzeRes.json();
      descriptions = analyzeJson.descriptions;
      
      setStatus('Generating narration...');
      setStepActive(3); // Update step BEFORE the call

      // 4. Generate TTS
      const ttsRes = await fetch('/generate-tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id, descriptions, tts_voice: ttsVoiceSelect.value })
      });
      if (!ttsRes.ok) throw new Error('Error generating narration');
      const ttsJson = await ttsRes.json();
      audio_chunks = ttsJson.audio_chunks;
      
      setStatus('Creating final video...');
      setStepActive(4); // Update step BEFORE the call

      // 5. Assemble video
      const assembleRes = await fetch('/assemble-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id, filename: filename_server, audio_chunks })
      });
      if (!assembleRes.ok) throw new Error('Error assembling the final video');
      const assembleJson = await assembleRes.json();
      video_b64 = assembleJson.video_b64;
      
      setStatus('Done!');
      setStepActive(4); // Keep the last step as 'done' or a final state if defined

      // Show results
      let html = `<div class='result-card'>`;
      if (descriptions && descriptions.length) {
        html += `<h2>Segment descriptions</h2><ul class='description-list'>`;
        descriptions.forEach((d, i) => {
          html += `<li><strong>Segment ${i + 1}:</strong> ${d}</li>`;
        });
        html += `</ul>`;
      }
      if (video_b64) {
        html += `<h2>Video with narration</h2><video controls style='max-width:100%;border-radius:8px;background:#000;margin-top:10px'><source src='data:video/mp4;base64,${video_b64}' type='video/mp4'></video>`;
      }
      html += `<div class='info'>Language: <code>${usedLang}</code> &nbsp;|&nbsp; Voice: <code>${usedVoice}</code></div>`;
      html += `<div class='info'>Video ID: <code>${video_id}</code></div>`;
      if (frames && frames.length) {
        html += `<details><summary>Show frame paths</summary><ul style='font-size:0.95em;'>`;
        frames.forEach(f => {
          html += `<li>${f}</li>`;
        });
        html += `</ul></details>`;
      }
      html += `</div>`;
      result.innerHTML = html;
      result.scrollIntoView({ behavior: 'smooth', block: 'start' });
      if (video_id) renderAskBlock(video_id);
      fileInput.value = '';
      updateFilename();
    } catch (err) {
      let errorStep = 0;
      if (!video_id) errorStep = 0;
      else if (!frames) errorStep = 1;
      else if (!descriptions) errorStep = 2;
      else if (!audio_chunks) errorStep = 3;
      else errorStep = 4;
      
      setStatus('Error: ' + (err.message || err));
      setStepActive(errorStep); // Mark the step where the error occurred
      if(stepProgressBar) stepProgressBar.style.display = 'flex';
      submitBtn.disabled = false;
      let html = `<div class='error'>${err.message || err}</div>`;
      if (descriptions && descriptions.length) {
        html += `<div class='result-card'><h2>Segment descriptions (partial)</h2><ul class='description-list'>`;
        descriptions.forEach((d, i) => {
          html += `<li><strong>Segment ${i + 1}:</strong> ${d}</li>`;
        });
        html += `</ul></div>`;
      }
      result.innerHTML = html;
    }
  });

  // --- Ask about the video block ---
  function renderAskBlock(videoId) {
    let askBlock = document.getElementById('askBlock');
    if (!askBlock) {
      askBlock = document.createElement('div');
      askBlock.id = 'askBlock';
      askBlock.className = 'ask-block';
      askBlock.innerHTML = `
        <h2>Ask about this video</h2>
        <form id="askForm" autocomplete="off" style="margin-bottom:10px;">
          <input type="text" id="askInput" placeholder="Type your question..." style="width:70%;padding:8px;" required />
          <button type="submit" style="padding:8px 18px;margin-left:8px;">Ask</button>
        </form>
        <div id="askHistory" class="ask-history"></div>
      `;
      result.appendChild(askBlock);
    }
    const askForm = document.getElementById('askForm');
    const askInput = document.getElementById('askInput');
    const askHistory = document.getElementById('askHistory');
    askForm.onsubmit = async function(ev) {
      ev.preventDefault();
      const question = askInput.value.trim();
      if (!question) return;
      askInput.disabled = true;
      askForm.querySelector('button').disabled = true;
      const msg = document.createElement('div');
      msg.className = 'ask-q';
      msg.innerHTML = `<strong>You:</strong> ${question}`;
      askHistory.appendChild(msg);
      // Dummy backend call (replace with real endpoint)
      let answer = '';
      try {
        const res = await fetch('/ask-video', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ video_id: videoId, question })
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        answer = data.answer || '[No answer]';
      } catch (err) {
        answer = '[Error: ' + err.message + ']';
      }
      const ans = document.createElement('div');
      ans.className = 'ask-a';
      ans.innerHTML = `<strong>Assistant:</strong> ${answer}`;
      askHistory.appendChild(ans);
      askInput.value = '';
      askInput.disabled = false;
      askForm.querySelector('button').disabled = false;
      askHistory.scrollTop = askHistory.scrollHeight;
    };
  }
});
