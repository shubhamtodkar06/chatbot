// chat.js - Main application logic with AudioNode connection order fix

// --- IMPORTANT: Path to the AudioWorklet processor file ---
// This path is defined in index.html and needs to be accessible here.
// const audioProcessorUrl = '/static/chat/audio-processor.js'; // This line is in index.html

// Declare variables and functions that need a wider scope
let isRecording = false;
let mediaStream = null;
let websocket = null; // WebSocket instance
let shouldStartRecordingAfterConnect = false; // Flag for click-to-start after connection

// Web Audio API components - Declared in wider scope
let audioContext = null;
let audioSourceNode = null;
let audioWorkletNode = null; // Use AudioWorkletNode

// VAD Parameters (Adjust as needed based on testing) - Frontend VAD only for stopping recording
let vadThreshold = 0.008; // Lower threshold for quieter environments, higher for noisy (0.0 to 1.0)
let vadSilenceDurationThreshold = 1500; // How long (ms) of silence to trigger stop
let vadSilenceTimer = null; // Timer ID for the silence timeout
let vadLastSpeechTime = 0; // Timestamp of the last time speech (above threshold) was detected
let vadSpeechGracePeriod = 500; // Time (ms) after speech ends to allow sending final chunk before silence timer starts

// === Declare element references (will be assigned in DOMContentLoaded) ===
let chatMessages = null;
let userInput = null;
let sendButton = null;
let initialSuggestionsList = null;
let dynamicSuggestionsList = null;
let voiceToggleBtn = null; // Voice Toggle Button
let voiceStatus = null; // Voice Status indicator
let botAudioPlayback = null; // Audio element for playback


// --- Helper function to update voice status UI ---
function updateVoiceStatus(statusText) {
    if (voiceStatus) { // Check if element is assigned
        voiceStatus.textContent = statusText;
    } else {
        console.warn("updateVoiceStatus: voiceStatus element not found yet.");
    }
}

// --- Helper function to update voice button state and related inputs ---
function setVoiceButtonState(text, disabled, isRecordingState = false) {
    if (voiceToggleBtn && userInput && sendButton) { // Check if elements are assigned
        voiceToggleBtn.textContent = text;
        voiceToggleBtn.disabled = disabled;

        // Add/remove 'recording' class for styling
        if (isRecordingState) {
            voiceToggleBtn.classList.add('recording');
        } else {
            voiceToggleBtn.classList.remove('recording');
        }

        // Also manage text input/send button state
        // They should be disabled when voice is active (connecting, processing, speaking, or listening/recording)
        const voiceIsActive = (text === 'Connecting...' || text === 'Processing...' || text === 'Speaking...' || isRecordingState);

        if (voiceIsActive) {
            userInput.disabled = true;
            sendButton.disabled = true;
        } else { // Voice is idle, ready, or had an error - allow text input
            // Re-enable only if a token is present
            const currentToken = localStorage.getItem('access_token');
            if (currentToken) {
                userInput.disabled = false;
                sendButton.disabled = false;
            } else {
                userInput.disabled = true;
                sendButton.disabled = false;
            }
        }
    } else {
        console.warn("setVoiceButtonState: UI elements not found yet.");
    }
}

// --- Function to display messages ---
function displayMessage(message, sender) {
    if (chatMessages) { // Check if element is assigned
        const messageContainer = document.createElement('div');
        messageContainer.classList.add('message-container');
        messageContainer.classList.add(sender === 'user' ? 'user-message' : 'bot-message');

        const messageDiv = document.createElement('div');
        messageDiv.classList.add(sender === 'user' ? 'user-message-bubble' : 'bot-message-bubble');
        messageDiv.textContent = message; // Use textContent to prevent XSS

        const timestampSpan = document.createElement('span');
        timestampSpan.classList.add('message-timestamp');
        const now = new Date();
        const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        timestampSpan.textContent = timeString;

        messageContainer.appendChild(messageDiv);
        messageContainer.appendChild(timestampSpan);
        chatMessages.appendChild(messageContainer); // Append to the chat messages container
        chatMessages.scrollTop = chatMessages.scrollHeight; // Auto-scroll to the latest message
    } else {
        console.warn("displayMessage: chatMessages element not found yet.");
    }
}


// --- Function to load initial suggestions ---
function loadInitialSuggestions() {
    const currentToken = localStorage.getItem('access_token');
    if (currentToken && initialSuggestionsList) { // Check if element is assigned
        fetch('/api/chat/suggestions/', { // Adjust URL if needed
            headers: {
                'Authorization': `Bearer ${currentToken}`
            }
        })
        .then(response => {
            if (!response.ok) {
                console.error('HTTP error loading suggestions:', response.status);
                if (response.status === 401 || response.status === 403) {
                    alert("Session expired. Please log in again.");
                    window.location.href = '/api/users/'; // Redirect to login URL
                }
                return Promise.reject('HTTP error');
            }
            return response.json();
        })
        .then(data => {
            if (data && data.suggestions) {
                initialSuggestionsList.innerHTML = ''; // Clear existing
                data.suggestions.forEach(product => {
                    const listItem = document.createElement('li');
                    listItem.textContent = product.name;
                    initialSuggestionsList.appendChild(listItem);
                });
            }
        })
        .catch(error => console.error('Error loading suggestions:', error));
    } else if (!currentToken) {
        console.warn("No token found, skipping loading initial suggestions.");
    } else {
        console.warn("loadInitialSuggestions: initialSuggestionsList element not found yet.");
    }
}


// --- Function to send text message ---
function sendTextMessage(message) {
    const currentToken = localStorage.getItem('access_token');
    if (message && currentToken && userInput && sendButton) { // Check if elements are assigned
        displayMessage(message, 'user');
        userInput.value = '';
        // Disable inputs while text message is processing
        userInput.disabled = true;
        sendButton.disabled = true;

        fetch('/api/chat/send/', { // Adjust URL if needed
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}`
            },
            body: JSON.stringify({ message: message })
        })
        .then(response => {
            if (!response.ok) {
                console.error('HTTP error sending message:', response.status);
                if (response.status === 401 || response.status === 403) {
                    alert("Session expired. Please log in again.");
                    window.location.href = '/api/users/'; // Redirect to login
                }
                return Promise.reject('HTTP error');
            }
            return response.json();
        })
        .then(data => {
            if (data && data.response) {
                displayMessage(data.response, 'bot');
            } else if (data && data.error) {
                displayMessage(`Error: ${data.error}`, 'bot');
            }

            // Handle dynamic product suggestions for text response
            if (dynamicSuggestionsList) { // Check if element is assigned
                 dynamicSuggestionsList.innerHTML = ''; // Clear previous suggestions
                 if (data && data.suggested_products) {
                     data.suggested_products.forEach(product => {
                         const productLi = document.createElement('li');
                         productLi.classList.add('dynamic-suggestion-item');
                         productLi.textContent = `${product.name} (${product.category})`;
                          // Add click listener to dynamic suggestions if needed
                          // productLi.addEventListener('click', () => sendTextMessage(`Tell me about ${product.name}`)); // Example listener
                         dynamicSuggestionsList.appendChild(productLi);
                     });
                 }
            } else {
                 console.warn("sendTextMessage: dynamicSuggestionsList element not found yet.");
            }
        })
        .catch(error => {
            console.error('Error sending message:', error);
            displayMessage('Error sending message. Please try again.', 'bot');
        })
        .finally(() => {
            // Re-enable text inputs after response, respecting voice state
             if (!isRecording && (!websocket || websocket.readyState !== WebSocket.CONNECTING)) {
                 const currentToken = localStorage.getItem('access_token');
                 if (currentToken) {
                     userInput.disabled = false;
                     sendButton.disabled = false;
                 }
             }
        });
    } else if (!currentToken) {
        console.warn("No token found, cannot send text message.");
        alert("You are not logged in.");
    } else {
        console.warn("sendTextMessage: UI elements not found yet.");
    }
}


// ===============================================================
// --- JavaScript for Voice Conversation (AudioWorklet & WebSocket) ---
// ===============================================================

// --- Function to initialize WebSocket connection ---
function connectWebSocket() {
    console.log("Attempting to connect WebSocket...");

    // Clear any existing connection first
    if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
        console.log("Closing existing WebSocket connection.");
        websocket.close();
    }

    // Get the token from localStorage
    const currentToken = localStorage.getItem('access_token');

    if (!currentToken) {
        console.error("No JWT token found. Cannot connect WebSocket.");
        updateVoiceStatus("Login Required");
        setVoiceButtonState("Login Required", true);
        return;
    }

    // Construct the WebSocket URL with the JWT (assuming your backend expects it this way)
    // IMPORTANT: Replace with your actual WebSocket URL pattern
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${wsScheme}://${window.location.host}/ws/chat/voice/?token=${currentToken}`; // Adjust URL if needed
    console.log("Connecting WebSocket to:", wsUrl);

    try {
        websocket = new WebSocket(wsUrl);

        const connectionTimeout = setTimeout(() => {
            if (websocket && websocket.readyState === WebSocket.CONNECTING) {
                console.error("WebSocket connection timeout after 5 seconds");
                websocket.close();
                updateVoiceStatus("Connection timeout");
                setVoiceButtonState("Start Voice Chat", false);
                shouldStartRecordingAfterConnect = false;
            }
        }, 5000); // 5-second timeout

        websocket.onopen = (event) => {
            clearTimeout(connectionTimeout);
            console.log('WebSocket connection opened:', event);
            updateVoiceStatus("Connected");
             // Only set button to 'Start' if we are not pending a recording start
            if (!shouldStartRecordingAfterConnect) {
                setVoiceButtonState("Start Voice Chat", false);
            }

            // Start recording if button was clicked while connecting
            if (shouldStartRecordingAfterConnect) {
                shouldStartRecordingAfterConnect = false;
                console.log("Starting recording automatically after connection.");
                // Add a small delay to ensure everything is ready
                setTimeout(() => startRecording(), 100); // Call startRecording from the wider scope
            }
        };

        websocket.onclose = (event) => {
            console.log('WebSocket connection closed:', event);
            updateVoiceStatus("Disconnected");
             // Ensure recording is stopped and UI reset
            if (isRecording) {
                const wasRecording = isRecording; // Capture state before stopping
                stopRecording(); // Call stopRecording from the wider scope
                 if(wasRecording) { // Only show error if we were actively recording
                     displayMessage("Voice chat disconnected. Please try again.", 'bot');
                 }
            }
            setVoiceButtonState("Start Voice Chat", false);
            shouldStartRecordingAfterConnect = false; // Reset flag
            websocket = null; // Clear websocket reference
        };

        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateVoiceStatus("Connection Error");
             // Ensure recording is stopped and UI reset
            if (isRecording) {
                 const wasRecording = isRecording; // Capture state before stopping
                stopRecording(); // Call stopRecording from the wider scope
                if(wasRecording) { // Only show error if we were actively recording
                    displayMessage("Voice chat error. Please try again.", 'bot');
                }
            } else {
                 displayMessage("WebSocket connection error. Please try refreshing the page.", 'bot');
             }

            setVoiceButtonState("Start Voice Chat", false);
            shouldStartRecordingAfterConnect = false; // Reset flag
            websocket = null; // Clear websocket reference
        };

        websocket.onmessage = (event) => {
            // console.log('Main thread: Received message from WebSocket:', event); // <-- Can be noisy, uncomment if needed

            try {
                if (typeof event.data === 'string') {
                    const data = JSON.parse(event.data);
                    console.log('Main thread: Received JSON message from WebSocket:', data.type); // <-- ADD THIS LOG

                    if (data.type === 'status') {
                         console.log('Main thread: Status update from backend:', data.message, data.detail); // <-- ADD THIS LOG
                         // Update UI status based on backend messages
                         updateVoiceStatus(data.detail || data.message); // Prefer detail if available

                         // Potentially adjust button state based on status, but be careful not to conflict with recording state
                         if (data.message === 'ready') {
                              // Backend is ready for input. Only re-enable button if not currently recording.
                              if (!isRecording && (botAudioPlayback && (botAudioPlayback.paused || botAudioPlayback.ended))) {
                                   setVoiceButtonState("Start Voice Chat", false);
                              } else if (isRecording) {
                                   // If we receive 'ready' while recording, it might mean backend processed
                                   // a previous utterance and is ready for the next. Keep 'Listening...' state.
                                   updateVoiceStatus("Listening..."); // Ensure status is correct
                                   setVoiceButtonState("Stop Voice Chat", false, true);
                              } else if (botAudioPlayback && (!botAudioPlayback.paused || !botAudioPlayback.ended)) {
                                   // If we receive 'ready' while audio is playing, wait for playback to end.
                                    console.log("Main thread: Received 'ready' status while audio is playing. Will reset state after playback.");
                              } else if (!botAudioPlayback) {
                                  console.warn("Main thread: botAudioPlayback element not found when processing 'ready' status.");
                                   if (!isRecording) {
                                       setVoiceButtonState("Start Voice Chat", false);
                                   }
                              }


                         } else if (data.message === 'processing') {
                              updateVoiceStatus(data.detail || "Processing...");
                              setVoiceButtonState("Processing...", true);
                         } else if (data.message === 'speaking') {
                               updateVoiceStatus(data.detail || "Speaking...");
                              // Button state handled by audio playback events
                         } else if (data.message === 'No audio received.' || data.message === 'No speech detected.') {
                               // These messages might come if startRecording initiated but no speech was detected quickly
                               // Reset UI to ready state
                               if (!isRecording) { // Only reset if not actively recording
                                   updateVoiceStatus(data.detail || data.message); // Display the specific status message
                                   setVoiceButtonState("Start Voice Chat", false);
                               } else {
                                    console.warn("Main thread: Received 'No audio/speech' status while still recording.");
                                    // Keep recording state, perhaps just update status briefly?
                                    updateVoiceStatus(data.detail || data.message);
                               }
                          }


                    } else if (data.type === 'bot_response') {
                        console.log('Main thread: Received bot_response from backend.'); // <-- ADD THIS LOG
                         if (data.user_text && data.user_text.trim()) {
                            // Display the transcribed user message
                            displayMessage(data.user_text, 'user');
                         }
                        if (data.text && data.text.trim()) {
                            // Display the bot's text response
                            displayMessage(data.text, 'bot');
                        }

                        // Handle dynamic product suggestions for text response
                        if (dynamicSuggestionsList) { // Check if element is assigned
                            dynamicSuggestionsList.innerHTML = ''; // Clear previous suggestions
                            if (data.suggested_products && Array.isArray(data.suggested_products)) {
                                data.suggested_products.forEach(product => {
                                    const productLi = document.createElement('li');
                                    productLi.classList.add('dynamic-suggestion-item');
                                    productLi.textContent = `${product.name} (${product.category})`;
                                     // Add click listener to dynamic suggestions if needed
                                     // productLi.addEventListener('click', () => sendTextMessage(`Tell me about ${product.name}`)); // Example listener
                                    dynamicSuggestionsList.appendChild(productLi);
                                });
                            }
                        } else {
                             console.warn("Main thread: dynamicSuggestionsList element not found when processing bot_response.");
                        }

                        // Reset UI state after receiving final response (text/suggestions)
                        // If audio is also sent, the AudioPlayback `onended` will handle the final UI reset.
                        // We only reset here if *no* audio is expected after this message type.
                        // Assuming audio comes as a separate binary message *after* bot_response text:
                        // Do NOT reset UI state here if audio is expected. The audio playback end handles it.
                        console.log("Main thread: Received bot_response text. Waiting for audio or next status.");


                    } else if (data.type === 'transcript_interim') {
                        console.log('Main thread: Received interim transcript:', data.transcript); // <-- ADD THIS LOG
                        // Optionally display interim transcript somewhere in the UI
                    }
                    else if (data.type === 'warning') {
                         console.warn('Main thread: Received warning from backend:', data.message, data.detail); // <-- ADD THIS LOG
                         // Display warnings to the user if appropriate
                         updateVoiceStatus(`Warning: ${data.detail || data.message}`);
                          // Consider if warning should reset UI state
                         if (!isRecording && (botAudioPlayback && (botAudioPlayback.paused || botAudioPlayback.ended))) {
                             setVoiceButtonState("Start Voice Chat", false);
                         }

                    }
                    else if (data.type === 'error') {
                        console.error('Main thread: Received error from backend:', data.message, data.detail); // <-- ADD THIS LOG
                        displayMessage(`Error: ${data.detail || data.message}`, 'bot');
                        updateVoiceStatus("Error");
                        setVoiceButtonState("Start Voice Chat", false); // Allow user to try again
                    } else if (data.type === 'processor_error') { // Handle messages from the Worklet's catch block
                         console.error('Main thread: Received Audio Processor Error from Worklet:', data.message, data.error); // <-- ADD THIS LOG
                          // You might want to stop recording and inform the user
                          if (isRecording) {
                               stopRecording(); // Call stopRecording from the wider scope
                               displayMessage("An audio processing error occurred. Please try again.", 'bot');
                          }
                           updateVoiceStatus("Audio Processor Error");
                           setVoiceButtonState("Start Voice Chat", false);

                    } else {
                        console.log('Main thread: Received unknown JSON message type:', data.type, data); // <-- ADD THIS LOG
                    }


                } else if (event.data instanceof Blob) {
                    // Handle audio responses (if your server sends audio)
                    console.log('Main thread: Received binary audio response (Blob)'); // <-- ADD THIS LOG
                    const audioUrl = URL.createObjectURL(event.data);

                    if (botAudioPlayback) { // Check if element is assigned
                        botAudioPlayback.src = audioUrl;
                        botAudioPlayback.style.display = 'none'; // Keep hidden

                        botAudioPlayback.onplay = () => {
                            console.log('Main thread: Audio playback started.'); // <-- ADD THIS LOG
                            updateVoiceStatus("Speaking...");
                            setVoiceButtonState("Speaking...", true); // Disable button while speaking
                        };

                        botAudioPlayback.onended = () => {
                            console.log("Main thread: Audio playback ended."); // <-- ADD THIS LOG
                            // Only reset UI state if not currently recording
                            if (!isRecording) {
                                updateVoiceStatus("Ready");
                                setVoiceButtonState("Start Voice Chat", false); // Re-enable after speaking
                            } else {
                                 // If recording immediately started after speaking, keep 'Listening...' state
                                updateVoiceStatus("Listening...");
                                setVoiceButtonState("Stop Voice Chat", false, true);
                            }
                            URL.revokeObjectURL(audioUrl); // Clean up the temporary URL
                        };

                         botAudioPlayback.onerror = (e) => {
                             console.error('Main thread: Error playing audio:', e); // <-- ADD THIS LOG
                             updateVoiceStatus("Audio Playback Error");
                             setVoiceButtonState("Start Voice Chat", false); // Re-enable on error
                             URL.revokeObjectURL(audioUrl); // Clean up
                         };

                         console.log('Main thread: Attempting to play audio...'); // <-- ADD THIS LOG
                        // Play the audio
                        botAudioPlayback.play().catch(error => {
                            console.error('Main thread: Error caught trying to play audio:', error); // <-- ADD THIS LOG
                            updateVoiceStatus("Audio Playback Error");
                            setVoiceButtonState("Start Voice Chat", false);
                             URL.revokeObjectURL(audioUrl); // Clean up
                        });
                    } else {
                        console.warn("Main thread: botAudioPlayback element not found."); // <-- ADD THIS LOG
                         URL.revokeObjectURL(audioUrl); // Still clean up URL
                         updateVoiceStatus("Audio Element Missing");
                         setVoiceButtonState("Start Voice Chat", false);
                    }
                } else {
                     console.log('Main thread: Received message of unknown type:', event.data); // <-- ADD THIS LOG
                 }
            } catch (error) {
                console.error('Main thread: Error processing WebSocket message:', error); // <-- ADD THIS LOG
                displayMessage("An error occurred processing the response.", 'bot');
                updateVoiceStatus("Message Error");
                setVoiceButtonState("Start Voice Chat", false);
            }
        };

        // Handle errors from the AudioWorklet node port
        // Attach these listeners *after* the node is created.
        // These listeners are now attached inside startRecording after node creation.
        // if (audioWorkletNode && audioWorkletNode.port) { // Check if node and port exist
        //     audioWorkletNode.port.onstatechange = (event) => {
        //          console.log('Main thread: AudioWorklet port state changed:', event.target.state); // <-- ADD THIS LOG
        //          if (event.target.state === 'closed') {
        //              console.error('Main thread: AudioWorklet port closed unexpectedly.'); // <-- ADD THIS LOG
        //              if (isRecording) {
        //                  stopRecording(); // Stop recording on port closure
        //                  displayMessage("Voice input error. Please try again.", 'bot');
        //              }
        //              updateVoiceStatus("Audio Error");
        //              setVoiceButtonState("Start Voice Chat", false);
        //          }
        //      };
        // } else {
        //      console.warn("Main thread: AudioWorkletNode or port not available to attach statechange listener."); // <-- ADD THIS LOG
        // }


        // Handle errors emitted by the processor itself (e.g., inside process method)
        // Attach these listeners *after* the node is created.
        // These listeners are now attached inside startRecording after node creation.
        // if (audioWorkletNode) { // Check if node exists
        //      audioWorkletNode.onprocessorerror = (event) => {
        //         console.error('Main thread: AudioWorklet processor error event:', event.detail); // <-- ADD THIS LOG
        //         if (isRecording) {
        //             stopRecording(); // Stop recording on processor error
        //              displayMessage("Voice processing error. Please try again.", 'bot');
        //         }
        //          updateVoiceStatus("Processor Error Event");
        //          setVoiceButtonState("Start Voice Chat", false);
        //      };
        // } else {
        //      console.warn("Main thread: AudioWorkletNode not available to attach processorerror listener."); // <-- ADD THIS LOG
        // }


    } catch (error) {
        console.error('Error creating WebSocket object:', error); // Keep this log
        updateVoiceStatus("WS Init Error");
        setVoiceButtonState("Start Voice Chat", false);
        shouldStartRecordingAfterConnect = false;
    }
}


// --- Function to start recording ---
async function startRecording() { // This function is now in the wider scope
    console.log("--- Entering startRecording() ---"); // Keep this log

    if (isRecording) {
        console.log("Already recording, ignoring start request"); // Keep this log
        return;
    }

     // Ensure WebSocket is open
     if (!websocket || websocket.readyState !== WebSocket.OPEN) {
         console.warn("Cannot start recording: WebSocket not open. State:",
                 websocket ? websocket.readyState : 'null'); // Keep this log
         updateVoiceStatus("WebSocket not ready");
         setVoiceButtonState("Start Voice Chat", false);
         return;
     }

    try {
        // Initialize or resume AudioContext
        if (!audioContext || audioContext.state === 'closed') {
             console.log("Creating new AudioContext..."); // Keep this log
            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                 sampleRate: 16000, // Specify sample rate (common for speech)
                 latencyHint: 'interactive'
             });
            console.log(`AudioContext created. Sample rate: ${audioContext.sampleRate} Hz`); // Keep this log

            // Add the AudioWorklet module - IMPORTANT!
            try {
                 // audioProcessorUrl is expected to be defined in index.html
                 if (typeof audioProcessorUrl === 'undefined') {
                     throw new Error("audioProcessorUrl is not defined in index.html");
                 }
                 await audioContext.audioWorklet.addModule(audioProcessorUrl);
                 console.log('AudioWorklet module added successfully.'); // Keep this log
            } catch (e) {
                console.error('Failed to add AudioWorklet module:', e); // Keep this log
                // Propagate this error to the main catch block
                throw new Error(`Failed to load audio processor: ${e.message}`);
            }


        } else if (audioContext.state === 'suspended') {
            await audioContext.resume();
            console.log('AudioContext resumed.'); // Keep this log
        }


        // Get microphone access
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                sampleRate: 16000 // Request 16kHz sample rate
            }
        });
        console.log('Microphone access granted.'); // Keep this log
        mediaStream = stream;

        // Create audio processing pipeline: source -> worklet -> destination
        audioSourceNode = audioContext.createMediaStreamSource(stream);
        console.log('MediaStreamSource created.'); // <-- ADD THIS LOG

        // Create the AudioWorkletNode BEFORE connecting to it
        // 'audio-processor' must match the name registered in audio-processor.js
        // Try explicitly setting input and output channel counts
        console.log('Creating AudioWorkletNode...'); // <-- ADD THIS LOG
        audioWorkletNode = new AudioWorkletNode(audioContext, 'audio-processor', {
            numberOfInputs: 1, // Assuming mono microphone input
            numberOfOutputs: 1 // Start by trying 1 output channel
            // If 1 output doesn't work, try numberOfOutputs: 2 to match the destination
            // numberOfOutputs: 2
        });
        console.log('AudioWorkletNode created with explicit channels.'); // Keep this log


        // Listen for messages from the AudioWorklet processor
        // This handler needs to be attached *after* the node is created.
        audioWorkletNode.port.onmessage = (event) => {
            console.log('Main thread: Received message from AudioWorklet:', event.data.type); // <-- ADD THIS LOG

            if (event.data.type === 'audio_data') {
                console.log('Main thread: Received audio_data message from Worklet.'); // <-- ADD THIS LOG
                const audioData = event.data.buffer; // ArrayBuffer from the processor
                console.log(`Main thread: Audio data buffer size: ${audioData.byteLength} bytes.`); // <-- ADD THIS LOG
                console.log('Main thread: Type of received audio data:', typeof audioData); // <-- ADD THIS LOG (Should be 'object')
                console.log('Main thread: Is received audio data ArrayBuffer?', audioData instanceof ArrayBuffer); // <-- ADD THIS LOG (Should be true)


                if (isRecording && websocket && websocket.readyState === WebSocket.OPEN) {
                    console.log('Main thread: WebSocket is open and recording is active. Sending audio data.'); // <-- ADD THIS LOG
                    try {
                        websocket.send(audioData);
                        console.log('Main thread: Successfully sent audio data via WebSocket.'); // <-- ADD THIS LOG
                    } catch (e) {
                        console.error('Main thread: Error sending audio data via WebSocket:', e); // <-- ADD THIS LOG
                        // Consider stopping recording on send error
                        stopRecording(); // Call stopRecording from the wider scope
                    }
                } else {
                    console.log('Main thread: WebSocket not open or recording not active. Not sending audio data.'); // <-- ADD THIS LOG
                    // ... (existing logic for discarding or stopping) ...
                    if (!isRecording) {
                        console.log("Main thread: Discarding audio data - recording stopped.");
                    } else if (!websocket || websocket.readyState !== WebSocket.OPEN) {
                        console.warn("Main thread: WebSocket not open, stopping recording from worklet message.");
                        stopRecording(); // Call stopRecording from the wider scope
                    }
                }
            } else if (event.data.type === 'vad_rms') {
                console.log('Main thread: Received vad_rms message from Worklet:', event.data.rms); // <-- ADD THIS LOG
                const rms = event.data.rms;
                const currentTime = Date.now(); // Use Date.now() for VAD timestamps

                // Process RMS for VAD in the main thread
                if (rms > vadThreshold) {
                   // Speech detected
                    vadLastSpeechTime = currentTime;

                    // Clear any silence timer since speech was detected
                    if (vadSilenceTimer) {
                        clearTimeout(vadSilenceTimer);
                        vadSilenceTimer = null;
                        // console.log("VAD (main): Speech detected, clearing silence timer."); // Keep noisy logs commented
                    }
                } else {
                   // Silence detected
                    const silenceDuration = currentTime - vadLastSpeechTime;

                    // Start silence timer if not already running and silence duration exceeds grace period
                    if (isRecording && vadSilenceTimer === null && silenceDuration >= vadSpeechGracePeriod) {
                        console.log(`VAD (main): Silence detected for > ${vadSpeechGracePeriod}ms. Starting silence timer.`); // Keep this log

                        vadSilenceTimer = setTimeout(() => {
                            console.log(`VAD (main): Silence threshold (${vadSilenceDurationThreshold}ms) reached. Stopping recording.`); // Keep this log
                            stopRecording(); // Call stopRecording from the wider scope
                             // vadSilenceTimer = null; // Cleared within stopRecording
                        }, vadSilenceDurationThreshold);
                    }
                   // Note: Audio sending is handled by the 'audio_data' message type
                }
            } else if (event.data.type === 'processor_error') {
                console.error('Main thread: Received processor_error from Worklet:', event.data.message, event.data.error); // <-- ADD THIS LOG
                 // You might want to stop recording and inform the user
                 if (isRecording) {
                      stopRecording(); // Call stopRecording from the wider scope
                      displayMessage("An audio processing error occurred. Please try again.", 'bot');
                 }
                  updateVoiceStatus("Audio Processor Error");
                  setVoiceButtonState("Start Voice Chat", false);
            }

             // Add other message types from the processor if needed
        };

        // Handle errors from the AudioWorklet node port
        // Attach these listeners *after* the node is created.
        if (audioWorkletNode && audioWorkletNode.port) { // Check if node and port exist
            audioWorkletNode.port.onstatechange = (event) => {
                 console.log('Main thread: AudioWorklet port state changed:', event.target.state); // <-- ADD THIS LOG
                 if (event.target.state === 'closed') {
                     console.error('Main thread: AudioWorklet port closed unexpectedly.'); // <-- ADD THIS LOG
                     if (isRecording) {
                         stopRecording(); // Stop recording on port closure
                         displayMessage("Voice input error. Please try again.", 'bot');
                     }
                     updateVoiceStatus("Audio Error");
                     setVoiceButtonState("Start Voice Chat", false);
                 }
             };
        } else {
             console.warn("Main thread: AudioWorkletNode or port not available to attach statechange listener."); // <-- ADD THIS LOG
        }


        // Handle errors emitted by the processor itself (e.g., inside process method)
        // Attach these listeners *after* the node is created.
        if (audioWorkletNode) { // Check if node exists
             audioWorkletNode.onprocessorerror = (event) => {
                console.error('Main thread: AudioWorklet processor error event:', event.detail); // <-- ADD THIS LOG
                if (isRecording) {
                    stopRecording(); // Stop recording on processor error
                     displayMessage("Voice processing error. Please try again.", 'bot');
                }
                 updateVoiceStatus("Processor Error Event");
                 setVoiceButtonState("Start Voice Chat", false);
             };
        } else {
             console.warn("Main thread: AudioWorkletNode not available to attach processorerror listener."); // <-- ADD THIS LOG
        }


        // *** FIX: CONNECT THE SOURCE TO THE WORKLET AFTER CREATING THE WORKLET ***
        console.log('Main thread: Connecting MediaStreamSource to AudioWorkletNode.'); // <-- ADD THIS LOG
        audioSourceNode.connect(audioWorkletNode); // <--- THIS IS THE CORRECTED ORDER


        // Connect the worklet to the destination (still recommended to keep context alive)
        console.log('Main thread: Connecting AudioWorkletNode to AudioContext destination.'); // <-- ADD THIS LOG
        audioWorkletNode.connect(audioContext.destination);


        isRecording = true;
        updateVoiceStatus("Listening...");
        setVoiceButtonState("Stop Voice Chat", false, true); // Button says stop, is enabled, and styled as recording
        vadLastSpeechTime = Date.now(); // Initialize last speech time
        vadSilenceTimer = null; // Ensure timer is clear on start


        console.log("--- startRecording() successful. Listening... ---"); // Keep this log

    } catch (error) {
        console.error('Error starting recording:', error); // Keep this log
        updateVoiceStatus(`Mic Error: ${error.message}`);
        setVoiceButtonState("Start Voice Chat", false);
        isRecording = false; // Ensure flag is false on error

        // Clean up resources
        if (mediaStream) {
            mediaStream.getTracks().forEach(track => track.stop());
            console.log('Main thread: Microphone tracks stopped.'); // <-- ADD THIS LOG
            mediaStream = null;
        }

        if (audioSourceNode) {
            audioSourceNode.disconnect();
            audioSourceNode = null;
             console.log("Main thread: audioSourceNode disconnected."); // <-- ADD THIS LOG
        }

         if (audioWorkletNode) { // Disconnect and remove message listener for Worklet
             audioWorkletNode.disconnect();
              if (audioWorkletNode.port) {
                  audioWorkletNode.port.onmessage = null; // Remove listener before closing
                  audioWorkletNode.port.onstatechange = null;
                  console.log('Main thread: AudioWorkletNode port listeners removed.'); // <-- ADD THIS LOG
              }
             audioWorkletNode = null;
             console.log("Main thread: audioWorkletNode disconnected."); // <-- ADD THIS LOG
         }

         // Consider suspending or closing AudioContext on severe error
         if (audioContext && audioContext.state !== 'suspended' && audioContext.state !== 'closed') {
             console.log("Main thread: Suspending AudioContext after error."); // <-- ADD THIS LOG
             audioContext.suspend().catch(e => console.error("Main thread: Error suspending AudioContext:", e));
             // Or audioContext.close() if you don't expect to use it again soon
         } else if (audioContext && audioContext.state === 'closed') {
             console.log("Main thread: AudioContext was already closed."); // <-- ADD THIS LOG
         }


    }
}

// --- Function to stop recording ---
function stopRecording() { // This function is now in the wider scope
    console.log("--- Entering stopRecording() ---"); // Keep this log
    if (!isRecording) {
        console.log("Not currently recording, can't stop."); // Keep this log
        // Ensure UI is in a non-recording state if this happens unexpectedly
        setVoiceButtonState("Start Voice Chat", false, false);
        updateVoiceStatus("Ready");
        return;
    }

    isRecording = false; // Set this flag immediately
    console.log("Stopping recording..."); // Keep this log
    updateVoiceStatus("Processing..."); // Indicate backend is working
    setVoiceButtonState("Processing...", true, false); // Button disabled, not recording style


    // Clear VAD timer if active
    if (vadSilenceTimer) {
        clearTimeout(vadSilenceTimer);
        vadSilenceTimer = null;
        console.log("Main thread: Silence timer cleared."); // <-- ADD THIS LOG
    }
    vadLastSpeechTime = 0; // Reset VAD state


    // Stop and clean up audio resources
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        console.log('Main thread: Microphone tracks stopped.'); // <-- ADD THIS LOG
        mediaStream = null;
    }

    if (audioSourceNode) {
        audioSourceNode.disconnect();
        audioSourceNode = null;
         console.log("Main thread: audioSourceNode disconnected."); // <-- ADD THIS LOG
    }

     if (audioWorkletNode) { // Disconnect and remove message listener for Worklet
         audioWorkletNode.disconnect();
          if (audioWorkletNode.port) {
              audioWorkletNode.port.onmessage = null; // Remove listener before closing
              audioWorkletNode.port.onstatechange = null;
              console.log('Main thread: AudioWorkletNode port listeners removed.'); // <-- ADD THIS LOG
          }
         audioWorkletNode = null;
         console.log("Main thread: audioWorkletNode disconnected."); // <-- ADD THIS LOG
     }

     // Suspend AudioContext when done recording to release resources
     // Only suspend if it's not already suspended or closed
     if (audioContext && audioContext.state !== 'suspended' && audioContext.state !== 'closed') {
         console.log("Main thread: Suspending AudioContext."); // <-- ADD THIS LOG
         audioContext.suspend().catch(e => console.error("Main thread: Error suspending AudioContext:", e));
     } else if (audioContext && audioContext.state === 'closed') {
         console.log("Main thread: AudioContext was already closed."); // <-- ADD THIS LOG
     }


    // Signal end of audio stream to the server (using JSON message)
    // For continuous STT, 'stop_recording' signals end of utterance,
    // NOT necessarily end of the entire WebSocket audio stream.
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log("Main thread: Sending stop_recording signal to backend via WebSocket."); // <-- ADD THIS LOG
        try {
            websocket.send(JSON.stringify({ type: 'stop_recording' }));

            // Set a timeout in case backend doesn't respond after stop signal
            // The timeout should be longer than typical processing time
            setTimeout(() => {
                // Check if the state is *still* 'Processing...' after the timeout
                // and not recording anymore.
                if (voiceStatus && voiceStatus.textContent === "Processing..." && !isRecording) { // Check if voiceStatus is assigned
                    console.warn("Main thread: Timeout waiting for backend response after stop_recording. Resetting state."); // <-- ADD THIS LOG
                    updateVoiceStatus("Ready");
                    setVoiceButtonState("Start Voice Chat", false);
                }
            }, 15000); // Increased timeout to 15 seconds - adjust if needed

        } catch (e) {
            console.error("Main thread: Error sending stop_recording signal:", e); // <-- ADD THIS LOG
             // If sending the stop signal fails, reset UI immediately
            updateVoiceStatus("Error Stopping");
            setVoiceButtonState("Start Voice Chat", false);
        }

        // Note: We typically keep the WebSocket open to receive the bot's response
        // after the stop_recording signal in a back-and-forth conversation.
    } else {
        console.warn("Main thread: WebSocket not open when attempting to send stop_recording signal."); // <-- ADD THIS LOG
        updateVoiceStatus("Disconnected");
        setVoiceButtonState("Start Voice Chat", false);
    }

    console.log("--- Exiting stopRecording() ---"); // Keep this log
}


// --- DOMContentLoaded: Assign elements and set up initial state/listeners ---
document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOMContentLoaded fired. Assigning UI elements and setting up initial listeners.");

    // Assign element references here
    chatMessages = document.getElementById('chat-messages');
    userInput = document.getElementById('user-input');
    sendButton = document.getElementById('send-button');
    initialSuggestionsList = document.getElementById('suggestions-list');
    dynamicSuggestionsList = document.getElementById('dynamic-suggestions-list');
    voiceToggleBtn = document.getElementById('voiceToggleBtn');
    voiceStatus = document.getElementById('voiceStatus');
    botAudioPlayback = document.getElementById('botAudioPlayback');

    // Add initial event listeners after elements are assigned
    if (sendButton && userInput) {
        sendButton.addEventListener('click', () => {
            const message = userInput.value.trim();
            sendTextMessage(message); // Call sendTextMessage from wider scope
        });

        userInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter' && !userInput.disabled) {
                event.preventDefault();
                sendButton.click();
            }
        });
    } else {
        console.error("DOMContentLoaded: Send button or user input not found.");
    }

    // Add click listeners to initial and dynamic suggestions using event delegation
    document.addEventListener('click', (event) => {
        if (event.target.closest('#suggestions-list li')) {
            const suggestionText = event.target.textContent;
             const message = `Tell me about ${suggestionText}`;
            sendTextMessage(message); // Call sendTextMessage from wider scope
        } else if (event.target.closest('#dynamic-suggestions-list li')) {
             const suggestionText = event.target.textContent;
             const cleanSuggestion = suggestionText.split('(')[0].trim();
             const message = `More about ${cleanSuggestion}`;
             sendTextMessage(message); // Call sendTextMessage from wider scope
        }
    });


    // --- Voice Toggle Button Handler ---
    if (voiceToggleBtn) { // Check if element is assigned
        voiceToggleBtn.addEventListener('click', async () => { // Made async for getUserMedia and addModule
            console.log("Voice Toggle Button clicked."); // Keep this log

            // First check authentication
            const tokenCheck = localStorage.getItem('access_token');
            if (!tokenCheck) {
                console.error("No token found. Cannot perform voice action."); // Keep this log
                updateVoiceStatus("Login Required");
                setVoiceButtonState("Login Required", true);
                alert("Please log in to use voice chat.");
                return;
            }

            // If currently recording, always stop
            if (isRecording) {
                console.log("Currently recording, stopping manually."); // Keep this log
                stopRecording(); // Call stopRecording from the wider scope
                return;
            }

            // Not recording - check WebSocket state
            if (!websocket || websocket.readyState === WebSocket.CLOSED || websocket.readyState === WebSocket.CLOSING) {
                // No active connection or connection is closing/closed - create new one
                console.log("No active WebSocket connection. Creating new one..."); // Keep this log
                updateVoiceStatus("Connecting...");
                setVoiceButtonState("Connecting...", true);
                shouldStartRecordingAfterConnect = true; // Set flag to start recording once connected
                connectWebSocket(); // Call connectWebSocket from the wider scope
            }
            else if (websocket.readyState === WebSocket.CONNECTING) {
                // Connection in progress - set flag to start recording when ready
                console.log("WebSocket connecting, will start recording when ready"); // Keep this log
                updateVoiceStatus("Connecting...");
                setVoiceButtonState("Connecting...", true);
                shouldStartRecordingAfterConnect = true;
            }
            else if (websocket.readyState === WebSocket.OPEN) {
                // Connection ready - start recording
                console.log("WebSocket ready, starting recording"); // Keep this log
                startRecording(); // Call startRecording from the wider scope
            }
        });
    } else {
        console.error("DOMContentLoaded: Voice toggle button not found.");
    }


    // Initial checks and setup after DOM is ready
    const token = localStorage.getItem('access_token');
    if (!token) {
        console.error('JWT token not found in localStorage during DOMContentLoaded. Chat features disabled.');
         // UI elements are already disabled by the check outside DOMContentLoaded
        updateVoiceStatus("Login Required");
    } else {
        console.log("JWT token found in localStorage during DOMContentLoaded. Initializing...");
         // UI elements are already enabled by the check outside DOMContentLoaded
        updateVoiceStatus("Ready");
        // Attempt to connect WebSocket on load if token exists
        // The timeout ensures UI elements are assigned before connectWebSocket is called
        setTimeout(() => {
            connectWebSocket(); // Call connectWebSocket from the wider scope
        }, 500);
    }

}); // End of DOMContentLoaded
