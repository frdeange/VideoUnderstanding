// scripts.js - Lógica JS para el frontend de VideoUnderstanding

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

  // Drag & drop
  uploadArea.addEventListener('click', (e) => {
    // Evita doble apertura si el click viene del input file
    if (e.target === fileInput) return;
    fileInput.click();
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
  // Form submit
  document.getElementById('uploadForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!fileInput.files.length) return;
    submitBtn.disabled = true;
    progress.style.display = 'block';
    progressBar.style.width = '0%';
    result.innerHTML = '';
    const data = new FormData();
    data.append('file', fileInput.files[0]);
    try {
      // Progress simulation (since fetch doesn't support upload progress natively)
      let fakeProgress = 0;
      const interval = setInterval(() => {
        fakeProgress = Math.min(95, fakeProgress + Math.random() * 10);
        progressBar.style.width = fakeProgress + '%';
      }, 200);
      const res = await fetch('/analyze', { method: 'POST', body: data });
      clearInterval(interval);
      progressBar.style.width = '100%';
      progress.style.display = 'none';
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const json = await res.json();
      // handle new response with descriptions array and optional video
      const { descriptions, video } = json;
      let html = `<div class='result-card'>`;
      if (descriptions && descriptions.length) {
        html += `<h2>Descripciones por segmentos</h2><ul class='description-list'>`;
        descriptions.forEach((d, i) => {
          html += `<li><strong>Segmento ${i + 1}:</strong> ${d}</li>`;
        });
        html += `</ul>`;
      }
      if (video) {
        html += `<h2>Vídeo con narración</h2><video controls src="data:video/mp4;base64,${video}" style="width:100%;"></video>`;
      } else {
        html += `<div class='error'>No se pudo generar el vídeo con narración.</div>`;
      }
      html += '</div>';
      result.innerHTML = html;
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    } catch (err) {
      progress.style.display = 'none';
      result.innerHTML = `<div class='error'>${err instanceof Error ? err.message : err}</div>`;
    } finally {
      submitBtn.disabled = false;
    }
  });
});
