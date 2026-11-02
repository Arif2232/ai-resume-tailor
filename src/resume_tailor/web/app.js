const token = document.querySelector('meta[name="app-token"]').content;
const byId = id => document.getElementById(id);
const setup = byId('setup');
const fileInput = byId('resume-file');
const resumeText = byId('resume-text');
const jobText = byId('job-text');
const jobUrl = byId('job-url');
const provider = byId('provider');
const model = byId('model');
const customModel = byId('custom-model');
const customWrap = byId('custom-model-wrap');
const apiKey = byId('api-key');
const workspaceId = byId('workspace-id');
const consent = byId('consent');
const generated = byId('tailored-text');
const confirmFacts = byId('confirm');
const exportButtons = [byId('copy'), byId('download-pdf'), byId('download-docx')];
let providers = {};
let resumeRevision = 0;
let jobRevision = 0;
let settingsRevision = 0;
let draftRevision = 0;
let sourceChanged = false;
let hasResult = false;
let draftEdited = false;

function feedback(element, message, error = false) {
  element.textContent = message;
  element.classList.toggle('error', error);
  element.hidden = !message;
}

async function requestJson(path, data) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-App-Token': token }, body: JSON.stringify(data) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Something went wrong. Please try again.');
  return result;
}

function messageFor(error) {
  return error instanceof TypeError ? 'Could not connect to the app. Check your connection and try again.' : error.message || 'Something went wrong. Please try again.';
}

function updateExports() {
  for (const button of exportButtons) button.disabled = !hasResult || sourceChanged || !confirmFacts.checked;
}

function sourceWasChanged() {
  if (!hasResult) return;
  sourceChanged = true;
  confirmFacts.checked = false;
  byId('result-badge').textContent = 'Inputs changed';
  feedback(byId('export-status'), 'Your inputs changed. Generate a new draft before exporting.', true);
  updateExports();
}

resumeText.addEventListener('input', () => { resumeRevision++; sourceWasChanged(); });
jobText.addEventListener('input', () => { jobRevision++; sourceWasChanged(); });
generated.addEventListener('input', () => {
  draftRevision++;
  draftEdited = true;
  confirmFacts.checked = false;
  feedback(byId('export-status'), '');
  updateExports();
});
confirmFacts.addEventListener('change', updateExports);

fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  if (!file) return;
  if (resumeText.value.trim() && !window.confirm('Replace the current resume text with the selected file?')) {
    fileInput.value = '';
    return;
  }
  const name = file.name.toLowerCase();
  const filename = name.endsWith('.pdf') ? 'resume.pdf' : name.endsWith('.docx') ? 'resume.docx' : '';
  if (!filename || file.size > 5_000_000) {
    feedback(byId('resume-status'), 'Choose a PDF or DOCX smaller than 5 MB.', true);
    return;
  }
  const revision = resumeRevision;
  fileInput.disabled = true;
  feedback(byId('resume-status'), 'Reading your resume…');
  try {
    const response = await fetch('/api/resume', { method: 'POST', headers: { 'X-App-Token': token, 'X-Resume-Filename': filename }, body: file });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not read the file.');
    if (revision !== resumeRevision) throw new Error('The text changed while the file was being read. Your edits were kept.');
    resumeText.value = result.text;
    resumeRevision++;
    sourceWasChanged();
    feedback(byId('resume-status'), `Resume loaded. ${(result.warnings || []).join(' ')}`);
  } catch (error) {
    feedback(byId('resume-status'), messageFor(error), true);
  } finally {
    fileInput.disabled = false;
  }
});

byId('import-job').addEventListener('click', async () => {
  if (!jobUrl.value.trim()) {
    feedback(byId('job-status'), 'Enter a public job link first.', true);
    return;
  }
  if (jobText.value.trim() && !window.confirm('Replace the current job description with the imported text?')) return;
  const revision = jobRevision;
  const button = byId('import-job');
  button.disabled = true;
  feedback(byId('job-status'), 'Importing the job description…');
  try {
    const result = await requestJson('/api/job-url', { url: jobUrl.value.trim() });
    if (revision !== jobRevision) throw new Error('The description changed during import. Your edits were kept.');
    jobText.value = result.text;
    jobRevision++;
    sourceWasChanged();
    feedback(byId('job-status'), 'Job description imported. Check it for missing details.');
  } catch (error) {
    feedback(byId('job-status'), messageFor(error), true);
  } finally {
    button.disabled = false;
  }
});

function selectedModel() {
  return model.value === 'custom' ? customModel.value.trim() : model.value;
}

function clearConnection() {
  settingsRevision++;
  feedback(byId('connection-status'), '');
}

function updateModel() {
  const isCustom = model.value === 'custom';
  customWrap.hidden = !isCustom;
  customModel.disabled = !isCustom;
  customModel.required = isCustom;
}

function updateProvider(clearKey = true) {
  const config = providers[provider.value];
  model.replaceChildren();
  if (!config) return;
  for (const item of config.models) model.add(new Option(item === config.default_model ? `${item} — suggested` : item, item));
  model.add(new Option('Other model…', 'custom'));
  if (clearKey) {
    apiKey.value = '';
    apiKey.type = 'password';
    byId('toggle-key').textContent = 'Show';
    byId('toggle-key').setAttribute('aria-label', 'Show API key');
    byId('toggle-key').setAttribute('aria-pressed', 'false');
  }
  workspaceId.value = '';
  byId('workspace-wrap').hidden = provider.value !== 'claude';
  workspaceId.disabled = provider.value !== 'claude';
  byId('key-link').href = config.key_url;
  byId('key-link').textContent = `Get an API key for ${config.label} ↗`;
  const note = byId('provider-note');
  note.replaceChildren();
  if (provider.value === 'gemini') note.append(document.createTextNode('Gemini free-tier content may be used to improve products. Check your plan. '));
  if (config.experimental) note.append(document.createTextNode('Claude is experimental and has not yet been live-verified. '));
  const pricing = document.createElement('a');
  pricing.href = config.pricing_url;
  pricing.target = '_blank';
  pricing.rel = 'noopener noreferrer';
  pricing.textContent = 'Pricing ↗';
  const privacy = document.createElement('a');
  privacy.href = config.privacy_url;
  privacy.target = '_blank';
  privacy.rel = 'noopener noreferrer';
  privacy.textContent = 'Data terms ↗';
  note.append(pricing, document.createTextNode(' · '), privacy);
  byId('consent-text').textContent = `I agree to send my resume text and job description to ${config.label}. API charges and its data terms may apply.`;
  consent.checked = false;
  updateModel();
}

provider.addEventListener('change', () => { clearConnection(); updateProvider(); });
model.addEventListener('change', () => { clearConnection(); updateModel(); });
for (const field of [apiKey, customModel, workspaceId]) field.addEventListener('input', clearConnection);
byId('toggle-key').addEventListener('click', () => {
  const show = apiKey.type === 'password';
  apiKey.type = show ? 'text' : 'password';
  byId('toggle-key').textContent = show ? 'Hide' : 'Show';
  byId('toggle-key').setAttribute('aria-label', show ? 'Hide API key' : 'Show API key');
  byId('toggle-key').setAttribute('aria-pressed', String(show));
});

async function loadOptions() {
  try {
    const response = await fetch('/api/options', { headers: { 'X-App-Token': token } });
    if (!response.ok) throw new Error('Could not load AI providers. Refresh the page.');
    providers = await response.json();
    provider.replaceChildren();
    for (const [name, config] of Object.entries(providers)) provider.add(new Option(config.label, name));
    updateProvider(false);
  } catch (error) {
    feedback(byId('generate-status'), messageFor(error), true);
  }
}

byId('test-provider').addEventListener('click', async () => {
  if (!provider.reportValidity() || !model.reportValidity() || !customModel.reportValidity() || !apiKey.reportValidity()) return;
  const revision = settingsRevision;
  const button = byId('test-provider');
  button.disabled = true;
  feedback(byId('connection-status'), 'Testing your connection…');
  try {
    const result = await requestJson('/api/test-provider', { provider: provider.value, model: selectedModel(), api_key: apiKey.value,
      workspace_id: workspaceId.disabled ? '' : workspaceId.value.trim() });
    if (revision === settingsRevision) feedback(byId('connection-status'), result.message);
  } catch (error) {
    if (revision === settingsRevision) feedback(byId('connection-status'), messageFor(error), true);
  } finally {
    button.disabled = false;
  }
});

function addText(parent, tag, text, className = '') {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  parent.append(element);
  return element;
}

function showResult(result) {
  generated.value = result.resume;
  draftRevision++;
  draftEdited = false;
  hasResult = true;
  sourceChanged = false;
  confirmFacts.checked = false;
  byId('empty-result').hidden = true;
  byId('result-content').hidden = false;
  byId('result-badge').textContent = 'Ready to review';
  feedback(byId('export-status'), '');
  const changes = byId('changes');
  changes.replaceChildren();
  for (const change of result.changes) {
    const item = document.createElement('li');
    addText(item, 'strong', 'Original');
    addText(item, 'p', change.before);
    addText(item, 'strong', 'Revised');
    addText(item, 'p', change.after);
    addText(item, 'p', `Why: ${change.reason}`);
    changes.append(item);
  }
  if (!result.changes.length) addText(changes, 'li', 'No source-backed change explanations were returned.');
  const alignment = byId('alignment');
  alignment.replaceChildren();
  for (const match of result.alignment) {
    const item = document.createElement('li');
    addText(item, 'strong', match.point);
    addText(item, 'p', `Resume: ${match.resume_evidence}`);
    addText(item, 'p', `Job: ${match.job_evidence}`);
    alignment.append(item);
  }
  if (!result.alignment.length) addText(alignment, 'li', 'No specific matches were identified.');
  const evidence = byId('evidence');
  evidence.replaceChildren();
  for (const section of result.sections) {
    for (const line of section.lines) {
      const item = document.createElement('div');
      item.className = 'evidence-item';
      addText(item, 'strong', line.text);
      addText(item, 'p', `Source: ${line.evidence.join(' · ')}`);
      evidence.append(item);
    }
  }
  const suggestions = byId('suggestions');
  suggestions.replaceChildren();
  for (const suggestion of result.suggestions) {
    const label = document.createElement('label');
    label.className = 'suggestion';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = suggestion.skill;
    const body = document.createElement('span');
    body.append(document.createTextNode(`I have ${suggestion.skill}`));
    addText(body, 'small', `Mentioned in the job: ${suggestion.job_evidence}`);
    label.append(checkbox, body);
    suggestions.append(label);
  }
  byId('suggestions-wrap').hidden = !result.suggestions.length;
  updateExports();
}

byId('add-skills').addEventListener('click', () => {
  const selected = [...byId('suggestions').querySelectorAll('input:checked:not(:disabled)')];
  if (!selected.length) {
    feedback(byId('export-status'), 'Select only the skills you actually have before adding them.', true);
    return;
  }
  generated.value = `${generated.value.trim()}\n\nSKILLS\n${selected.map(item => item.value).join(', ')}`;
  for (const item of selected) { item.checked = false; item.disabled = true; }
  draftRevision++;
  draftEdited = true;
  confirmFacts.checked = false;
  feedback(byId('export-status'), 'Confirmed skills added. Review the updated resume.');
  updateExports();
});

setup.addEventListener('submit', async event => {
  event.preventDefault();
  feedback(byId('generate-status'), '');
  if (!setup.reportValidity()) return;
  if (draftEdited && !window.confirm('Replace your edited draft with a new one?')) return;
  const revisions = [resumeRevision, jobRevision, settingsRevision, draftRevision];
  const button = byId('generate');
  button.disabled = true;
  feedback(byId('generate-status'), 'Creating your draft. This can take a moment…');
  try {
    const result = await requestJson('/api/tailor', { provider: provider.value, model: selectedModel(), api_key: apiKey.value,
      workspace_id: workspaceId.disabled ? '' : workspaceId.value.trim(), resume: resumeText.value,
      job_description: jobText.value, consent: consent.checked });
    if (revisions.some((value, index) => value !== [resumeRevision, jobRevision, settingsRevision, draftRevision][index])) {
      throw new Error('Your inputs or draft changed while generating. Your edits were kept; please generate again.');
    }
    showResult(result);
    feedback(byId('generate-status'), ['Draft ready. Review it and confirm its accuracy before exporting.', ...(result.warnings || [])].join(' '));
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    byId('result-heading').scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  } catch (error) {
    feedback(byId('generate-status'), messageFor(error), true);
  } finally {
    button.disabled = false;
  }
});

byId('copy').addEventListener('click', async () => {
  if (!confirmFacts.checked || sourceChanged) return;
  try {
    await navigator.clipboard.writeText(generated.value);
    feedback(byId('export-status'), 'Resume text copied.');
  } catch {
    generated.focus();
    generated.select();
    feedback(byId('export-status'), 'Select and copy the highlighted text using your keyboard.');
  }
});

async function download(format) {
  if (!confirmFacts.checked || sourceChanged) return;
  const button = byId(`download-${format}`);
  button.disabled = true;
  feedback(byId('export-status'), `Preparing your ${format === 'pdf' ? 'PDF' : 'Word file'}…`);
  try {
    const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-App-Token': token },
      body: JSON.stringify({ text: generated.value, format, confirmed: confirmFacts.checked }) });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not create the file.');
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = `tailored-resume.${format}`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    feedback(byId('export-status'), 'Your download is ready.');
  } catch (error) {
    feedback(byId('export-status'), messageFor(error), true);
  } finally {
    updateExports();
  }
}

byId('download-pdf').addEventListener('click', () => download('pdf'));
byId('download-docx').addEventListener('click', () => download('docx'));
loadOptions();
