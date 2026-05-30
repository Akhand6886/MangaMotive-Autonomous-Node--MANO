document.addEventListener('DOMContentLoaded', () => {
    // --- State ---
    let activeJobId = null;
    let activeJobTimer = null;
    let selectedStepId = null;
    let storyboardSlides = [];
    let playbackInterval = null;
    let currentSlideIndex = 0;

    // DOM Elements
    const tabButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');
    const pageTitle = document.getElementById('page-title');
    const pageDesc = document.getElementById('page-desc');
    const rawPromptText = document.getElementById('raw-prompt');
    const btnParsePrompt = document.getElementById('btn-parse-prompt');
    const parseSpinner = document.getElementById('parse-spinner');
    
    // Structured task form inputs
    const structuredCard = document.getElementById('structured-task-card');
    const taskTopic = document.getElementById('task-topic');
    const taskPlatform = document.getElementById('task-platform');
    const taskDuration = document.getElementById('task-duration');
    const taskStyle = document.getElementById('task-style');
    const taskAssets = document.getElementById('task-assets');
    const btnRunHarness = document.getElementById('btn-run-harness');

    // Execution elements
    const executionTimeline = document.getElementById('execution-timeline');
    const executionJobLbl = document.getElementById('execution-job-lbl');
    const evalBadge = document.getElementById('eval-badge');
    const metricFact = document.getElementById('metric-fact');
    const metricStyle = document.getElementById('metric-style');
    const metricEngagement = document.getElementById('metric-engagement');
    const auditErrorsContainer = document.getElementById('audit-errors-container');
    const auditErrorsList = document.getElementById('audit-errors-list');
    const terminalStdout = document.getElementById('terminal-stdout');
    
    // Final output elements
    const finalOutputCard = document.getElementById('final-output-card');
    const outputPackageType = document.getElementById('output-package-type');
    const outputSeoTitle = document.getElementById('output-seo-title');
    const outputSlug = document.getElementById('output-slug');
    const outputScriptText = document.getElementById('output-script-text');
    const outputMetaDescription = document.getElementById('output-meta-description');
    const outputKeywords = document.getElementById('output-keywords');
    const outputTags = document.getElementById('output-tags');
    const subtabButtons = document.querySelectorAll('.tab-sub-btn');
    const subtabContents = document.querySelectorAll('.tab-sub-content');

    // Media elements
    const videoCanvasSlide = document.getElementById('video-canvas-slide');
    const videoCanvasOverlay = document.getElementById('video-canvas-overlay');
    const btnVideoPlay = document.getElementById('btn-video-play');
    const videoScrubFill = document.getElementById('video-scrub-fill');
    const videoTime = document.getElementById('video-time');
    const videoAudioPreview = document.getElementById('video-audio-preview');

    // Memory Store Elements
    const memoryCardsContainer = document.getElementById('memory-cards-container');
    const btnSaveMemories = document.getElementById('btn-save-memories');
    const saveMemSpinner = document.getElementById('save-mem-spinner');

    // Job history elements
    const jobsTableBody = document.getElementById('jobs-table-body');

    // 1. Tab Switching Handler
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            switchTab(tabId);
        });
    });

    function switchTab(tabId) {
        tabButtons.forEach(b => {
            if (b.getAttribute('data-tab') === tabId) {
                b.classList.add('active');
            } else {
                b.classList.remove('active');
            }
        });
        
        tabPanes.forEach(pane => {
            if (pane.id === `tab-${tabId}`) {
                pane.classList.add('active');
            } else {
                pane.classList.remove('active');
            }
        });

        // Update Headers
        if (tabId === 'orchestrator') {
            pageTitle.textContent = "Executive Orchestrator";
            pageDesc.textContent = "Transform raw AI prompts into a structured thinking machine ecosystem.";
        } else if (tabId === 'execution') {
            pageTitle.textContent = "Active Execution Loop";
            pageDesc.textContent = "Monitor the real-time agent execution plan timeline and log outputs.";
            const execBadge = document.getElementById('execution-badge');
            if (execBadge) execBadge.classList.add('hidden');
            selectedStepId = null;  // Reset step inspection on tab re-entry
        } else if (tabId === 'memory') {
            pageTitle.textContent = "Cumulative Preference Memory";
            pageDesc.textContent = "Manage SQLite persistent guidelines, style preferences, and banned words.";
            loadMemorySettings();
        } else if (tabId === 'history') {
            pageTitle.textContent = "Job Archives";
            pageDesc.textContent = "Track execution results and details of past and historical pipeline runs.";
            loadJobsHistory();
        }
    }

    // Sub-tab switcher inside output representation
    subtabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const subtabId = btn.getAttribute('data-subtab');
            subtabButtons.forEach(b => b.classList.toggle('active', b === btn));
            subtabContents.forEach(pane => {
                pane.classList.toggle('active', pane.id === `subtab-${subtabId}`);
            });
        });
    });

    // 2. Interface Layer: Prompt Parsing
    btnParsePrompt.addEventListener('click', async () => {
        const text = rawPromptText.value.trim();
        if (!text) return alert("Please input a prompt to parse.");

        parseSpinner.classList.remove('hidden');
        btnParsePrompt.disabled = true;

        try {
            const response = await fetch('/api/harness/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: text })
            });

            if (!response.ok) throw new Error("Parser endpoint returned error code.");
            
            const task = await response.json();
            
            // Populate task inputs
            taskTopic.value = task.topic;
            taskPlatform.value = task.target_platform;
            taskDuration.value = task.duration;
            taskStyle.value = task.style;
            
            // Populate assets
            taskAssets.innerHTML = '';
            task.assets_needed.forEach(asset => {
                const badge = document.createElement('span');
                badge.className = 'tag';
                badge.textContent = asset;
                taskAssets.appendChild(badge);
            });

            // Enable Run Card
            structuredCard.classList.remove('disabled');
            btnRunHarness.disabled = false;

        } catch (error) {
            console.error("Parse Error:", error);
            alert("Failed to parse prompt. Using default task structure.");
            // Set defaults
            taskTopic.value = "Anime Spot";
            taskPlatform.value = "Editorial Blog";
            taskDuration.value = "800 words";
            taskStyle.value = "high-energy";
            taskAssets.innerHTML = '<span class="tag">Script</span><span class="tag">Thumbnail</span>';
            structuredCard.classList.remove('disabled');
            btnRunHarness.disabled = false;
        } finally {
            parseSpinner.classList.add('hidden');
            btnParsePrompt.disabled = false;
        }
    });

    // 3. Trigger Intelligence Harness Running
    btnRunHarness.addEventListener('click', async () => {
        const payload = {
            topic: taskTopic.value,
            target_platform: taskPlatform.value,
            duration: taskDuration.value,
            style: taskStyle.value,
            assets_needed: Array.from(taskAssets.querySelectorAll('.tag')).map(t => t.textContent)
        };

        try {
            const response = await fetch('/api/harness/trigger', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error("Job launch endpoint failed.");

            const job = await response.json();
            activeJobId = job.id;
            
            // Switch tabs
            switchTab('execution');
            
            // Update navigation indicator badge
            const executionBadge = document.getElementById('execution-badge');
            executionBadge.textContent = "RUNNING";
            executionBadge.classList.remove('hidden');

            // Setup logs and timeline empty state
            executionTimeline.innerHTML = '<div class="timeline-empty"><div class="spinner"></div><p>Decomposing goals and generating execution steps...</p></div>';
            terminalStdout.textContent = "Executive Planner wakes up. Initiating dynamic multi-agent planning...";
            
            // Start Poller
            startJobPoller(activeJobId);

        } catch (error) {
            console.error("Trigger Job Error:", error);
            alert("Could not start harness loop.");
        }
    });

    // 4. Job Poller Runtime (Deprecated polling, using WebSockets; runs one initial load)
    function startJobPoller(jobId) {
        if (activeJobTimer) clearInterval(activeJobTimer);
        pollJobState(jobId);
    }

    async function pollJobState(jobId) {
        try {
            const response = await fetch(`/api/jobs/${jobId}`);
            if (!response.ok) throw new Error("Polling job fetch error.");
            
            const job = await response.json();
            updateExecutionUI(job);
            
            if (job.status === 'completed' || job.status === 'failed') {
                clearInterval(activeJobTimer);
                activeJobTimer = null;
                const badge = document.getElementById('execution-badge');
                badge.textContent = job.status.toUpperCase();
                badge.style.backgroundColor = job.status === 'completed' ? 'var(--success)' : 'var(--danger)';
            }
        } catch (error) {
            console.error("Poll Error:", error);
        }
    }

    // 5. Update Active Execution Panel Elements
    function updateExecutionUI(job) {
        executionJobLbl.textContent = `Job ID: ${job.id} | Series: ${job.series_title} (${job.target_type})`;
        
        // Render Timeline Plan Steps
        const steps = job.execution_plan || [];
        if (steps.length === 0) return;

        executionTimeline.innerHTML = '';
        steps.forEach((step, idx) => {
            const node = document.createElement('div');
            node.className = `timeline-node ${step.status}`;
            node.setAttribute('data-step-id', step.step_id);
            node.innerHTML = `
                <h4>${idx + 1}. ${step.name}</h4>
                <p>Worker: <code>${step.worker}</code> | Status: ${step.status}</p>
            `;
            
            // Timeline step click inspection
            node.addEventListener('click', () => {
                selectedStepId = step.step_id;
                document.querySelectorAll('.timeline-node').forEach(n => n.style.borderColor = 'transparent');
                node.style.borderColor = 'var(--accent)';
                
                // Show output and logs in console terminal
                terminalStdout.textContent = `[INSPECTION STEP: ${step.name.toUpperCase()}]\n\n--- OUTPUT STRUCTURE ---\n${step.output || 'No output recorded yet.'}\n\n--- WORKER LOGS ---\n${step.log || 'Waiting for execution logs...'}`;
            });

            executionTimeline.appendChild(node);
        });

        // Set default console text scrolling to active node if not manually inspecting
        if (!selectedStepId) {
            const activeStep = steps.find(s => s.status === 'running') || steps.find(s => s.status === 'completed' && s.log);
            if (activeStep) {
                terminalStdout.textContent = `[AGENT LOGS: ${activeStep.name.toUpperCase()}]\n\n${activeStep.log}`;
                // Auto scroll terminal to bottom
                const termBody = document.querySelector('.terminal-body');
                termBody.scrollTop = termBody.scrollHeight;
            }
        }

        // Render evaluations (Layer 6)
        const evals = job.evaluations || {};
        if (Object.keys(evals).length > 0) {
            evalBadge.textContent = evals.passed ? "PASSED" : "FAILED STYLE/FACT AUDIT";
            evalBadge.style.backgroundColor = evals.passed ? 'var(--success)' : 'var(--danger)';
            metricFact.textContent = evals.fact_accuracy_score ? `${evals.fact_accuracy_score}/10` : '-';
            metricStyle.textContent = evals.style_compliance_score ? `${evals.style_compliance_score}/10` : '-';
            metricEngagement.textContent = evals.predicted_engagement_score ? `${evals.predicted_engagement_score}%` : '-';

            if (evals.errors && evals.errors.length > 0) {
                auditErrorsContainer.classList.remove('hidden');
                auditErrorsList.innerHTML = '';
                evals.errors.forEach(err => {
                    const li = document.createElement('li');
                    li.textContent = err;
                    auditErrorsList.appendChild(li);
                });
            } else {
                auditErrorsContainer.classList.add('hidden');
            }
        } else {
            evalBadge.textContent = "PENDING";
            evalBadge.style.backgroundColor = 'var(--border-color)';
            metricFact.textContent = '-';
            metricStyle.textContent = '-';
            metricEngagement.textContent = '-';
            auditErrorsContainer.classList.add('hidden');
        }

        // If completed, show deliverables representations
        if (job.status === 'completed') {
            finalOutputCard.classList.remove('hidden');
            outputPackageType.textContent = job.target_type === 'youtube_short' ? "YouTube Short Video Deliverable" : "Contentful Editorial Article Deliverable";
            
            // Map legacy and nested outputs
            const writerData = job.writer_data || {};
            const seoData = job.seo_data || {};
            const formatterData = job.formatter_data || {};
            const publisherData = job.publisher_data || {};

            outputSeoTitle.textContent = seoData.seo_title || writerData.draft_title || "Review Draft Completed";
            outputSlug.textContent = seoData.slug || "n/a";
            
            outputScriptText.textContent = writerData.draft_text || writerData.review_body_markdown || "Content text body complete.";
            outputMetaDescription.textContent = seoData.meta_description || "n/a";
            outputKeywords.textContent = seoData.keywords ? seoData.keywords.join(', ') : 'n/a';
            outputTags.textContent = seoData.tags ? seoData.tags.join(', ') : 'n/a';

            // Storyboard video rendering
            const pubAssets = publisherData.assets || {};
            const thumbUrl = pubAssets.thumbnail || "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800";
            const audioUrl = pubAssets.audio || "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3";
            
            videoCanvasSlide.src = thumbUrl;
            videoAudioPreview.src = audioUrl;

            // Load storyboard slides from steps if available (e.g. ffmpeg step output)
            const ffmpegStep = steps.find(s => s.worker === 'publishing_worker' || s.worker === 'voice_timing');
            if (ffmpegStep && ffmpegStep.output) {
                try {
                    const parsedOut = JSON.parse(ffmpegStep.output);
                    storyboardSlides = parsedOut.timing_map || [];
                    if (storyboardSlides.length > 0) {
                        videoCanvasOverlay.textContent = storyboardSlides[0].subtitle || "Narration ready.";
                    }
                } catch(e) {
                    storyboardSlides = [];
                    videoCanvasOverlay.textContent = "Playback content compiled.";
                }
            } else {
                storyboardSlides = [];
                videoCanvasOverlay.textContent = "Audio slide compile complete.";
            }

            populateStoryboardEditor(steps);

        } else {
            finalOutputCard.classList.add('hidden');
        }
    }

    // 6. Audio Storyboard Synchronization Playback Loops
    btnVideoPlay.addEventListener('click', () => {
        if (videoAudioPreview.paused) {
            videoAudioPreview.play();
            btnVideoPlay.textContent = "Pause Short";
            startStoryboardPlaybackTimer();
        } else {
            videoAudioPreview.pause();
            btnVideoPlay.textContent = "Play Short";
            stopStoryboardPlaybackTimer();
        }
    });

    function startStoryboardPlaybackTimer() {
        if (playbackInterval) clearInterval(playbackInterval);
        playbackInterval = setInterval(() => {
            const curTime = videoAudioPreview.currentTime;
            const duration = videoAudioPreview.duration || 60;
            const percentage = (curTime / duration) * 100;
            
            videoScrubFill.style.width = `${percentage}%`;
            
            // Format time display
            const mins = Math.floor(curTime / 60);
            const secs = Math.floor(curTime % 60);
            videoTime.textContent = `${mins}:${secs < 10 ? '0' : ''}${secs}`;

            // Sync visual slides if storyboard timings are loaded
            if (storyboardSlides.length > 0) {
                // Find matching slide timestamp
                const activeSlide = storyboardSlides.find((s, idx) => {
                    const start = s.start || idx * 10;
                    const end = s.end || (idx + 1) * 10;
                    return curTime >= start && curTime < end;
                }) || storyboardSlides[storyboardSlides.length - 1];

                if (activeSlide) {
                    videoCanvasOverlay.textContent = activeSlide.subtitle || activeSlide.text || "Narration ready.";
                    if (activeSlide.image_url && videoCanvasSlide.src !== activeSlide.image_url) {
                        videoCanvasSlide.src = activeSlide.image_url;
                    }
                }
            }

            if (videoAudioPreview.ended) {
                btnVideoPlay.textContent = "Play Short";
                videoScrubFill.style.width = "0%";
                videoTime.textContent = "0:00";
                stopStoryboardPlaybackTimer();
            }
        }, 200);
    }

    function stopStoryboardPlaybackTimer() {
        if (playbackInterval) {
            clearInterval(playbackInterval);
            playbackInterval = null;
        }
    }

    // 7. Memory Store management panel load & LLM Configuration
    const selectLlmProvider = document.getElementById('setting-llm-provider');
    const inputOpenaiModel = document.getElementById('setting-openai-model');
    const inputGeminiModel = document.getElementById('setting-gemini-model');
    const inputOpenaiKey = document.getElementById('setting-openai-key');
    const inputGeminiKey = document.getElementById('setting-gemini-key');

    if (selectLlmProvider) {
        selectLlmProvider.addEventListener('change', () => {
            toggleProviderFields(selectLlmProvider.value);
        });
    }

    function toggleProviderFields(provider) {
        const openaiFields = document.querySelectorAll('.config-field-openai');
        const geminiFields = document.querySelectorAll('.config-field-gemini');
        
        if (provider === 'openai') {
            openaiFields.forEach(f => f.classList.remove('hidden'));
            geminiFields.forEach(f => f.classList.add('hidden'));
        } else if (provider === 'gemini') {
            openaiFields.forEach(f => f.classList.add('hidden'));
            geminiFields.forEach(f => f.classList.remove('hidden'));
        } else {
            openaiFields.forEach(f => f.classList.add('hidden'));
            geminiFields.forEach(f => f.classList.add('hidden'));
        }
    }

    async function loadMemorySettings() {
        try {
            const response = await fetch('/api/harness/memory');
            const memories = await response.json();
            
            memoryCardsContainer.innerHTML = '';
            memories.forEach(mem => {
                const configKeys = ['llm_provider', 'openai_api_key', 'openai_model', 'gemini_api_key', 'gemini_model'];
                if (configKeys.includes(mem.key)) {
                    const val = mem.value && mem.value.length > 0 ? mem.value[0] : '';
                    if (mem.key === 'llm_provider' && selectLlmProvider) {
                        selectLlmProvider.value = val;
                        toggleProviderFields(val);
                    } else if (mem.key === 'openai_model' && inputOpenaiModel) {
                        inputOpenaiModel.value = val;
                    } else if (mem.key === 'gemini_model' && inputGeminiModel) {
                        inputGeminiModel.value = val;
                    } else if (mem.key === 'openai_api_key' && inputOpenaiKey) {
                        inputOpenaiKey.value = val;
                    } else if (mem.key === 'gemini_api_key' && inputGeminiKey) {
                        inputGeminiKey.value = val;
                    }
                    return;
                }

                const box = document.createElement('div');
                box.className = 'memory-box';
                box.innerHTML = `
                    <label>${mem.key.replaceAll('_', ' ')}</label>
                    <p style="font-size:11px; color:var(--text-secondary)">Guidelines separated by comma or newlines.</p>
                    <textarea data-key="${mem.key}" rows="4">${mem.value.join('\n')}</textarea>
                `;
                memoryCardsContainer.appendChild(box);
            });
        } catch (error) {
            console.error("Load Memory Error:", error);
        }
    }

    btnSaveMemories.addEventListener('click', async () => {
        saveMemSpinner.classList.remove('hidden');
        btnSaveMemories.disabled = true;

        const textareas = memoryCardsContainer.querySelectorAll('textarea');
        try {
            for (let ta of textareas) {
                const key = ta.getAttribute('data-key');
                const val = ta.value.split('\n').map(item => item.trim()).filter(item => item.length > 0);
                
                await fetch('/api/harness/memory', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: key, value: val })
                });
            }

            if (selectLlmProvider) {
                const configSettings = [
                    { key: 'llm_provider', value: [selectLlmProvider.value] },
                    { key: 'openai_model', value: [inputOpenaiModel.value || 'gpt-4o-mini'] },
                    { key: 'gemini_model', value: [inputGeminiModel.value || 'gemini-2.5-flash'] },
                    { key: 'openai_api_key', value: [inputOpenaiKey.value || ''] },
                    { key: 'gemini_api_key', value: [inputGeminiKey.value || ''] }
                ];

                for (let setting of configSettings) {
                    await fetch('/api/harness/memory', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(setting)
                    });
                }
            }

            alert("System settings and guidelines updated in database.");
        } catch (error) {
            console.error("Save Memory Error:", error);
            alert("Failed to save memory guidelines.");
        } finally {
            saveMemSpinner.classList.add('hidden');
            btnSaveMemories.disabled = false;
        }
    });

    // 8. Job Archives History Table Loading
    async function loadJobsHistory() {
        try {
            const response = await fetch('/api/jobs');
            const jobs = await response.json();
            
            jobsTableBody.innerHTML = '';
            if (jobs.length === 0) {
                jobsTableBody.innerHTML = '<tr><td colspan="6" class="text-center">No historical execution records found.</td></tr>';
                return;
            }

            jobs.forEach(job => {
                const tr = document.createElement('tr');
                
                // Format timestamp
                const date = new Date(job.created_at);
                const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

                tr.innerHTML = `
                    <td><code>${job.id.substring(0, 8)}...</code></td>
                    <td><strong>${job.series_title}</strong></td>
                    <td><code>${job.target_type}</code></td>
                    <td>${dateStr}</td>
                    <td><span class="badge-status status-${job.status}">${job.status.toUpperCase()}</span></td>
                    <td><button class="btn btn-small btn-inspect" data-job-id="${job.id}">Inspect</button></td>
                `;

                // Add inspector trigger
                tr.querySelector('.btn-inspect').addEventListener('click', () => {
                    activeJobId = job.id;
                    switchTab('execution');
                    // Immediately pull job state
                    pollJobState(activeJobId);
                });

                jobsTableBody.appendChild(tr);
            });
        } catch (error) {
            console.error("Load Jobs History Error:", error);
            jobsTableBody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">Failed to fetch historical database.</td></tr>';
        }
    }

    // 9. Download Deliverables Button
    const btnDownloadPackage = document.getElementById('btn-download-package');
    if (btnDownloadPackage) {
        btnDownloadPackage.addEventListener('click', async () => {
            if (!activeJobId) return alert("No active job found to download.");
            try {
                const response = await fetch(`/api/jobs/${activeJobId}`);
                if (!response.ok) throw new Error("Failed to fetch job data");
                const job = await response.json();
                
                // Construct the download package
                const downloadData = {
                    job_id: job.id,
                    series_title: job.series_title,
                    target_type: job.target_type,
                    title: job.writer_data?.draft_title || job.seo_data?.seo_title || "MANO Deliverables",
                    slug: job.seo_data?.slug || "",
                    script: job.writer_data?.draft_text || job.writer_data?.review_body_markdown || "",
                    metadata: {
                        description: job.seo_data?.meta_description || "",
                        keywords: job.seo_data?.keywords || [],
                        tags: job.seo_data?.tags || []
                    },
                    published_at: job.publisher_data?.published_at || new Date().toISOString()
                };

                const blob = new Blob([JSON.stringify(downloadData, null, 2)], { type: 'application/json' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `deliverables-${job.series_title.toLowerCase().replace(/\s+/g, '-')}-${job.id.substring(0, 8)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            } catch (error) {
                console.error("Download Error:", error);
                alert("Failed to export deliverables package.");
            }
        });
    }

    // Cleanup intervals on page unload to prevent memory leaks
    window.addEventListener('beforeunload', () => {
        if (activeJobTimer) clearInterval(activeJobTimer);
        if (playbackInterval) clearInterval(playbackInterval);
    });

    // --- WebSockets Event Hub Client ---
    let socket = null;
     
    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsUrl = `${wsProtocol}://${window.location.host}/api/ws/events`;
        socket = new WebSocket(wsUrl);
         
        socket.onopen = () => {
            console.log("WebSocket connected to Event Hub.");
        };
         
        socket.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                console.log("WS Event:", msg.type, msg.data);
                handleWebSocketEvent(msg.type, msg.data);
            } catch (e) {
                console.error("Error parsing WS message:", e);
            }
        };
         
        socket.onclose = () => {
            console.warn("WebSocket disconnected. Retrying connection in 3 seconds...");
            setTimeout(connectWebSocket, 3000);
        };
         
        socket.onerror = (err) => {
            console.error("WebSocket error:", err);
        };
    }

    async function handleWebSocketEvent(type, data) {
        if (type === 'job_updated' || type === 'job_completed') {
            const activeTab = document.querySelector('.nav-btn.active').getAttribute('data-tab');
            if (activeTab === 'history') {
                loadJobHistory();
            }
        }

        if (!activeJobId || data.job_id !== activeJobId) return;

        if (type === 'job_updated') {
            const response = await fetch(`/api/jobs/${activeJobId}`);
            if (response.ok) {
                const job = await response.json();
                updateExecutionUI(job);
            }
        } else if (type === 'step_started') {
            const node = document.querySelector(`[data-step-id="${data.step_id}"]`);
            if (node) {
                node.className = 'timeline-node running';
                const statusLbl = node.querySelector('p code');
                if (statusLbl) statusLbl.textContent = 'running';
            }
            const executionBadge = document.getElementById('execution-badge');
            executionBadge.textContent = "RUNNING";
            executionBadge.classList.remove('hidden');
        } else if (type === 'log_update') {
            if (!selectedStepId || selectedStepId === data.step_id) {
                const stepNode = document.querySelector(`[data-step-id="${data.step_id}"]`);
                const stepNameText = stepNode ? stepNode.querySelector('h4').textContent : "Active Agent";
                terminalStdout.textContent = `[AGENT LOGS: ${stepNameText.toUpperCase()}]\n\n${data.log}`;
                const termBody = document.querySelector('.terminal-body');
                termBody.scrollTop = termBody.scrollHeight;
            }
        } else if (type === 'eval_updated') {
            const evals = data.evaluations || {};
            evalBadge.textContent = evals.passed ? "PASSED" : "FAILED STYLE/FACT AUDIT";
            evalBadge.style.backgroundColor = evals.passed ? 'var(--success)' : 'var(--danger)';
            metricFact.textContent = evals.fact_accuracy_score ? `${evals.fact_accuracy_score}/10` : '-';
            metricStyle.textContent = evals.style_compliance_score ? `${evals.style_compliance_score}/10` : '-';
            metricEngagement.textContent = evals.predicted_engagement_score ? `${evals.predicted_engagement_score}%` : '-';

            if (evals.errors && evals.errors.length > 0) {
                auditErrorsContainer.classList.remove('hidden');
                auditErrorsList.innerHTML = '';
                evals.errors.forEach(err => {
                    const li = document.createElement('li');
                    li.textContent = err;
                    auditErrorsList.appendChild(li);
                });
            } else {
                auditErrorsContainer.classList.add('hidden');
            }
        } else if (type === 'step_completed') {
            const response = await fetch(`/api/jobs/${activeJobId}`);
            if (response.ok) {
                const job = await response.json();
                updateExecutionUI(job);
            }
        } else if (type === 'job_completed') {
            const badge = document.getElementById('execution-badge');
            badge.textContent = "COMPLETED";
            badge.style.backgroundColor = 'var(--success)';
            
            const response = await fetch(`/api/jobs/${activeJobId}`);
            if (response.ok) {
                const job = await response.json();
                updateExecutionUI(job);
            }
            
            const saveStoryboardSpinner = document.getElementById('save-storyboard-spinner');
            if (saveStoryboardSpinner) saveStoryboardSpinner.classList.add('hidden');
        }
    }

    // Initialize WebSocket
    connectWebSocket();

    // Storyboard slide populator
    function populateStoryboardEditor(steps) {
        const slidesList = document.getElementById('slides-editor-list');
        if (!slidesList) return;
        
        slidesList.innerHTML = '';
        
        const ffmpegStep = steps.find(s => s.worker === 'publishing_worker' || s.worker === 'voice_timing');
        if (!ffmpegStep || !ffmpegStep.output) {
            slidesList.innerHTML = '<div class="text-center py-2">No storyboard assets compiled yet.</div>';
            return;
        }
        
        try {
            const parsedOut = JSON.parse(ffmpegStep.output);
            const slides = parsedOut.timing_map || [];
            
            if (slides.length === 0) {
                slidesList.innerHTML = '<div class="text-center py-2">No storyboard slides compiled.</div>';
                return;
            }
            
            slides.forEach(slide => {
                const card = document.createElement('div');
                card.className = 'slide-edit-card';
                card.setAttribute('data-slide-number', slide.slide_number);
                
                const thumbUrl = slide.image_url || "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800";
                
                card.innerHTML = `
                    <div class="slide-edit-thumb">
                        <img src="${thumbUrl}" alt="Slide ${slide.slide_number}">
                    </div>
                    <div class="slide-edit-fields">
                        <div class="slide-edit-row">
                            <div class="slide-edit-group" style="flex: 1.5;">
                                <label>Narration Subtitle</label>
                                <textarea class="slide-subtitle-input" rows="2">${slide.subtitle || ''}</textarea>
                            </div>
                            <div class="slide-edit-group" style="flex: 2;">
                                <label>Image Generation Prompt</label>
                                <textarea class="slide-prompt-input" rows="2">${slide.image_prompt || ''}</textarea>
                            </div>
                        </div>
                        <div class="slide-edit-row" style="justify-content: space-between; align-items: center;">
                            <span style="font-size: 10px; color: var(--text-secondary);">
                                Time range: <code>${slide.start.toFixed(1)}s - ${slide.end.toFixed(1)}s</code>
                            </span>
                            <label class="slide-regen-toggle">
                                <input type="checkbox" class="slide-regen-chk">
                                <span>Regenerate Image</span>
                            </label>
                        </div>
                    </div>
                `;
                slidesList.appendChild(card);
            });
        } catch (e) {
            console.error("Error parsing storyboard slides for editor:", e);
            slidesList.innerHTML = '<div class="text-center py-2 text-danger">Error loading storyboard slides.</div>';
        }
    }

    // Save & Refine Storyboard button click handler
    const btnSaveStoryboard = document.getElementById('btn-save-storyboard');
    const saveStoryboardSpinner = document.getElementById('save-storyboard-spinner');
    
    if (btnSaveStoryboard) {
        btnSaveStoryboard.addEventListener('click', async () => {
            if (!activeJobId) return;
            
            const slideCards = document.querySelectorAll('.slide-edit-card');
            const slidesData = [];
            
            slideCards.forEach(card => {
                const slideNumber = parseInt(card.getAttribute('data-slide-number'));
                const subtitle = card.querySelector('.slide-subtitle-input').value;
                const imagePrompt = card.querySelector('.slide-prompt-input').value;
                const regenerateImage = card.querySelector('.slide-regen-chk').checked;
                
                const origSlide = storyboardSlides.find(s => s.slide_number === slideNumber) || {};
                
                slidesData.push({
                    slide_number: slideNumber,
                    start: origSlide.start || 0,
                    end: origSlide.end || 0,
                    subtitle: subtitle,
                    image_prompt: imagePrompt,
                    image_url: origSlide.image_url || null,
                    regenerate_image: regenerateImage
                });
            });
            
            try {
                if (saveStoryboardSpinner) saveStoryboardSpinner.classList.remove('hidden');
                btnSaveStoryboard.disabled = true;
                
                const response = await fetch(`/api/jobs/${activeJobId}/refine`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ slides: slidesData })
                });
                
                if (!response.ok) throw new Error("Storyboard refine request failed.");
                
                const res = await response.json();
                console.log("Refinement started:", res);
                
                switchTab('execution');
                terminalStdout.textContent = "Initiating selective storyboard refinement. Re-running specialized worker agents...";
                
            } catch (error) {
                console.error("Refine Storyboard Error:", error);
                alert("Could not process storyboard refinement.");
                if (saveStoryboardSpinner) saveStoryboardSpinner.classList.add('hidden');
            } finally {
                btnSaveStoryboard.disabled = false;
            }
        });
    }
});
