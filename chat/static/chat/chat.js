// chat.js - Main application logic with Integrated Voice Chat

// --- Element References (Declare here, assign in DOMContentLoaded) ---
let chatMessages = null;
let userInput = null;
let sendButton = null;
let initialSuggestionsList = null;
let dynamicSuggestionsList = null;
let voiceToggleBtn = null; // Add voice button ref
let voiceStatus = null; // Add voice status ref
// botAudioPlayback is defined in HTML, can get ref if needed, but new code uses `new Audio()`
// let botAudioPlayback = null;


// --- Voice Chat Variables (New) ---
let voiceSocket = null; // Renamed to avoid conflict if 'websocket' was used elsewhere
let speechRecognition = null;
let currentAudioQueue = [];
let isAudioPlaying = false;
let currentAudioElement = null; // Reference to the currently playing Audio object
let currentVoiceSessionId = null; // To link STT input to TTS output



document.addEventListener('DOMContentLoaded', function() {
    // Initialize element references
    chatMessages = document.getElementById('chat-messages');
    userInput = document.getElementById('user-input');
    sendButton = document.getElementById('send-button');
    initialSuggestionsList = document.getElementById('suggestions-list');
    dynamicSuggestionsList = document.getElementById('dynamic-suggestions-list');
    voiceToggleBtn = document.getElementById('voiceToggleBtn'); // Get button reference
    voiceStatus = document.getElementById('voiceStatus'); // Get status reference
    // botAudioPlayback = document.getElementById('botAudioPlayback'); // Get audio element ref if needed

    // Load initial suggestions
    loadInitialSuggestions();

    // Set up event listeners for text input
    if (sendButton && userInput) {
        sendButton.addEventListener('click', () => {
            const message = userInput.value.trim();
            if (message) {
                sendTextMessage(message);
            }
        });

        userInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && userInput.value.trim()) {
                sendTextMessage(userInput.value.trim());
            }
        });
    }

    // Set up voice toggle button listener (New)
    if (voiceToggleBtn) {
        voiceToggleBtn.addEventListener('click', toggleVoiceChat); // Use the new toggle function
        // Initial state: Disabled until WebSocket connects
        voiceToggleBtn.disabled = true;
    }

    // Initialize WebSocket connection immediately when DOM is ready (New)
    connectVoiceWebSocket();
});


// --- Helper function to update voice button state and related inputs ---
// (Keep this if you had one, or use the new helper below)
function updateVoiceButtonAndInputState(isVoiceActive) {
    if (voiceToggleBtn && userInput && sendButton) {
        if (isVoiceActive) {
            voiceToggleBtn.textContent = "Stop Voice Chat";
            voiceToggleBtn.classList.add('active-voice'); // Optional: Add a class for styling
            // Disable text input/send while in active voice mode
            userInput.disabled = true;
            sendButton.disabled = true;
        } else {
            voiceToggleBtn.textContent = "Start Voice Chat";
            voiceToggleBtn.classList.remove('active-voice'); // Optional: Remove class
            // Re-enable text input/send
            userInput.disabled = false;
            sendButton.disabled = false;
        }
    }
}

// --- Function to update voice status display ---
function updateVoiceStatus(statusText) {
    if (voiceStatus) {
        voiceStatus.textContent = statusText;
    }
}


// --- Function to display messages ---
function displayMessage(message, sender) {
    // (Keep your existing displayMessage function here)
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
    // (Keep your existing loadInitialSuggestions function here)
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
    // (Keep your existing sendTextMessage function here)
    const currentToken = localStorage.getItem('access_token');
    if (message && currentToken && userInput && sendButton) { // Check if elements are assigned
        displayMessage(message, 'user');
        userInput.value = '';
        // Disable inputs while text message is processing
        userInput.disabled = true;
        sendButton.disabled = true;
        // Disable voice toggle button temporarily if needed, respecting its connected state
        if (voiceToggleBtn && voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
            voiceToggleBtn.disabled = true;
        }


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
            // Re-enable text inputs after response
             if (!speechRecognition || !speechRecognition.recognizing) { // Re-enable unless actively doing voice STT
                 const currentToken = localStorage.getItem('access_token');
                 if (currentToken) {
                     userInput.disabled = false;
                     sendButton.disabled = false;
                 }
             }
            // Re-enable voice toggle if WebSocket is open
            if (voiceToggleBtn && voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
                voiceToggleBtn.disabled = false;
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
// --- JavaScript for Voice Conversation (Web Speech API & WebSocket) ---
// ===============================================================

// --- Toggle Voice Chat Function ---
function toggleVoiceChat() {
    if (!speechRecognition || !speechRecognition.recognizing) {
        startVoiceChat();
    } else {
        stopVoiceChat();
    }
}

// --- Start Voice Chat (Initialize STT) ---
function startVoiceChat() {
    // Ensure WebSocket is connected before starting voice
    if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN) {
        console.warn("WebSocket not connected. Cannot start voice chat.");
        // Optionally try to reconnect or inform user
        updateVoiceStatus("Connecting...");
        connectVoiceWebSocket(); // Attempt reconnect
        // Disable button until connected
        if(voiceToggleBtn) voiceToggleBtn.disabled = true;
        return;
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        updateVoiceStatus("Speech Recognition not supported");
        console.error("Speech Recognition API not supported in this browser.");
        return;
    }

    // Create new recognition instance if not exists or was stopped
    if (!speechRecognition) {
        speechRecognition = new SR();
        speechRecognition.interimResults = false; // Only return final results
        speechRecognition.continuous = true; // Keep listening
        speechRecognition.lang = "en-US"; // Set language

        speechRecognition.onstart = () => {
            updateVoiceStatus("Listening...");
            console.log("Speech Recognition started.");
            updateVoiceButtonAndInputState(true); // Set button/input state
        };

        speechRecognition.onend = () => {
            updateVoiceStatus("Idle");
            console.log("Speech Recognition ended. Restarting...");
            updateVoiceButtonAndInputState(false); // Reset button/input state temporarily

            // Auto-restart recognition after a short delay unless explicitly stopped
            // This is crucial for continuous listening as onend fires even after a result
            if (voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
                setTimeout(() => {
                    if (voiceSocket && voiceSocket.readyState === WebSocket.OPEN && !speechRecognition.recognizing) {
                        speechRecognition.start();
                    }
                }, 200); // Small delay before restarting
            } else {
                // If WS is closed, fully reset UI state
                updateVoiceButtonAndInputState(false);
                if (voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable start button
            }
        };

        speechRecognition.onerror = (event) => {
            console.error('Speech Recognition error:', event.error);
            updateVoiceStatus(`STT Error: ${event.error}`);
            // Error often stops recognition, onend will handle restart if WS is open
            updateVoiceButtonAndInputState(false);
            // Avoid infinite error loop if WS is also down
            if (!voiceSocket || voiceSocket.readyState !== WebSocket.OPEN) {
                if (voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable start button
            }
        };

        speechRecognition.onresult = (event) => {
            const last = event.results[event.results.length - 1];
            // Process only final results
            if (last.isFinal) {
                const text = last[0].transcript.trim();
                if (text) {
                    console.log("Recognized:", text);
                    displayMessage(text, 'user'); // Display user's recognized text

                    // --- Interrupt Bot Audio and Send to WebSocket ---
                    stopAudioPlayback(); // Stop any currently playing bot audio
                    currentAudioQueue.length = 0; // Clear the audio queue
                    isAudioPlaying = false;

                    // Generate a new session ID for this user utterance
                    currentVoiceSessionId = crypto.randomUUID();
                    updateVoiceStatus("Sending...");

                    // Send the recognized text to the WebSocket backend
                    if (voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
                        // REMOVE: const flowSlug = "setoo-ai-agent-oizt5ixbshazir_dsydpqa"; // Use your flow slug

                        voiceSocket.send(JSON.stringify({
                            text: text,
                            // REMOVE: flow_slug: flowSlug,
                            session_id: currentVoiceSessionId // Send the new session ID
                        }));
                        console.log(`Sent text to WS: "${text}" with session_id: ${currentVoiceSessionId}`); // REMOVE flow_slug from log
                    } else {
                        console.error("WebSocket not open, cannot send recognized text.");
                        updateVoiceStatus("WS Disconnected");
                        displayMessage("Voice chat disconnected. Please try again.", 'bot');
                        // Stop STT if WS is closed
                        speechRecognition.stop(); // onend will handle UI reset/restart attempt
                    }
                }
            }
        };
    }

    // Start the speech recognition
    try {
        speechRecognition.start();
        // updateVoiceButtonAndInputState(true); // State update also happens in onstart
    } catch (e) {
        console.error("Error starting Speech Recognition:", e);
        updateVoiceStatus("Error Starting STT");
        updateVoiceButtonAndInputState(false);
        if (voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable start button
    }
}

// --- Stop Voice Chat (Stop STT) ---
function stopVoiceChat() {
    if (speechRecognition && speechRecognition.recognizing) {
        speechRecognition.stop();
        console.log("Speech Recognition stopped manually.");
        // onend will handle status/button state update
        // Ensure audio playback is stopped when user stops voice chat
        stopAudioPlayback();
        currentAudioQueue.length = 0;
        isAudioPlaying = false;
        // Don't clear currentVoiceSessionId immediately, bot might still be responding
    } else {
        console.warn("Speech Recognition is not active.");
        // Ensure button state is correct even if STT wasn't recognizing
        updateVoiceButtonAndInputState(false);
    }
}

// --- Initialize WebSocket connection for Voice ---
function connectVoiceWebSocket() {
    console.log("Attempting to connect Voice WebSocket...");

    // Clear any existing connection first
    if (voiceSocket && (voiceSocket.readyState === WebSocket.OPEN || voiceSocket.readyState === WebSocket.CONNECTING)) {
        console.log("Closing existing Voice WebSocket connection.");
        voiceSocket.close();
    }

    // Get the token from localStorage - Using your existing authentication
    const currentToken = localStorage.getItem('access_token');

    if (!currentToken) {
        console.error("No JWT token found in localStorage. Cannot connect WebSocket.");
        updateVoiceStatus("Login Required");
        if(voiceToggleBtn) voiceToggleBtn.disabled = true; // Disable button
        return;
    }

    // Construct the WebSocket URL with the JWT from localStorage
    // This MUST match the URL pattern defined in your chat/routing.py (/ws/chat/voice/)
    const wsScheme = window.location.protocol === "https:" ? "wss" : "ws";
    // *** CHANGE THIS LINE: Use the existing path and include ONLY the token query param ***
    // We removed flow_slug from the backend consumer's expected query params
    const voiceWsUrl = `${wsScheme}://${window.location.host}/ws/chat/voice/?token=${currentToken}`;


    console.log("Connecting Voice WebSocket to:", voiceWsUrl);
    updateVoiceStatus("Connecting...");
    if(voiceToggleBtn) voiceToggleBtn.disabled = true; // Disable button while connecting

    try {
        voiceSocket = new WebSocket(voiceWsUrl);

        voiceSocket.onopen = (event) => {
            console.log('Voice WebSocket connection opened:', event);
            // The backend sends a 'ready' status message upon successful connection/thread setup
            // updateVoiceStatus("Connected. Click Start."); // Status update will come from backend
            if(voiceToggleBtn) voiceToggleBtn.disabled = false; // Enable button
        };

        voiceSocket.onclose = (event) => {
            console.log('Voice WebSocket connection closed:', event);
            updateVoiceStatus("Disconnected");
            // Ensure STT and audio are stopped on WS close
            stopVoiceChat(); // This also stops audio
            updateVoiceButtonAndInputState(false); // Reset UI state
            if(voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable button to allow reconnect attempt
            voiceSocket = null; // Clear socket reference

            // Optional: Attempt to auto-reconnect after a delay
            // setTimeout(connectVoiceWebSocket, 5000); // Reconnect after 5 seconds
        };

        voiceSocket.onerror = (error) => {
            console.error('Voice WebSocket error:', error);
            updateVoiceStatus("Connection Error");
            // Ensure STT and audio are stopped on WS error
            stopVoiceChat(); // This also stops audio
            updateVoiceButtonAndInputState(false); // Reset UI state
            if(voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable button
            voiceSocket = null; // Clear socket reference
            displayMessage("Voice chat connection error. Please try again.", 'bot');
        };

        voiceSocket.onmessage = (event) => {
            let msg;
            try {
                msg = JSON.parse(event.data);
                console.log("Received WebSocket message:", msg);
            } catch (e) {
                console.error("Failed to parse WebSocket message:", e);
                return;
            }

            // --- Handle different message types from the backend ---
            // Based on your consumer code, backend sends:
            // status: {'type': 'status', 'message': 'ready/processing/speaking', 'detail': '...'}
            // error: {'type': 'error', 'message': '...', 'detail': '...'}
            // bot_response: {'type': 'bot_response', 'user_text': ..., 'text': ..., 'suggested_products': [...]}
            // tts_chunk: {'event': 'tts_chunk', 'session_id': ..., 'payload': ..., 'mime': ...}


            if (msg.type === 'status') {
                // Update status display based on backend message
                updateVoiceStatus(msg.message === 'ready' ? "Connected. Click Start." : msg.message);
                console.log("Status detail:", msg.detail);
                 // If backend sends 'ready', re-enable the voice button if WS is open
                 if (msg.message === 'ready' && voiceToggleBtn && voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
                     voiceToggleBtn.disabled = false;
                 }
            } else if (msg.type === 'error') {
                console.error("Backend error message:", msg.detail);
                updateVoiceStatus(`Backend Error: ${msg.message}`);
                displayMessage(`Backend Error: ${msg.detail}`, 'bot');
                 // After an error, the backend sends a 'ready' status, which re-enables the button.
            } else if (msg.type === 'bot_response') {
                // This message contains the bot's text response and suggestions
                console.log("Received bot text response:", msg.text);
                displayMessage(msg.text, 'bot'); // Display the bot's text

                 // Display user's text received back from backend if needed (optional, already displayed on recognition)
                 // if (msg.user_text) { console.log("User text received back:", msg.user_text); }

                // Handle dynamic product suggestions for voice response
                if (dynamicSuggestionsList) {
                    dynamicSuggestionsList.innerHTML = ''; // Clear previous
                    if (msg.suggested_products) {
                         msg.suggested_products.forEach(product => {
                             const productLi = document.createElement('li');
                             productLi.classList.add('dynamic-suggestion-item');
                             productLi.textContent = `${product.name} (${product.category})`;
                             dynamicSuggestionsList.appendChild(productLi);
                         });
                    }
                }

            } else if (msg.event === "tts_chunk" && msg.payload && msg.session_id) {
                 // --- Handle TTS Chunk Message ---
                 // This message contains a base64 encoded audio chunk for playback

                 // IMPORTANT: Only process audio for the *current* voice session
                 if (msg.session_id !== currentVoiceSessionId) {
                     console.log(`Ignoring TTS chunk for old session: ${msg.session_id}`);
                     return;
                 }

                 // Decode base64 to audio blob
                 try {
                     const bytes = Uint8Array.from(atob(msg.payload), c => c.charCodeAt(0));
                     const blob = new Blob([bytes], { type: msg.mime || 'audio/mpeg' }); // Default to mp3 if mime is missing
                     console.log("Received and decoded TTS chunk for session:", msg.session_id);

                     // Enqueue the audio blob for playback
                     enqueueAudio(blob);

                 } catch (e) {
                     console.error("Error decoding or processing audio chunk:", e);
                     updateVoiceStatus("Audio Error");
                 }
            } else {
                // Received an unexpected message format
                console.warn("Received unknown or incomplete message format:", msg);
            }
        };

    } catch (e) {
        console.error("Error creating WebSocket:", e);
        updateVoiceStatus("Connection Failed");
        updateVoiceButtonAndInputState(false);
        if(voiceToggleBtn) voiceToggleBtn.disabled = false; // Re-enable button
        voiceSocket = null;
        displayMessage("Voice chat connection failed. Please check console.", 'bot');
    }
}

// --- Audio Playback Queue ---
function enqueueAudio(blob) {
    currentAudioQueue.push(blob);
    if (!isAudioPlaying) {
        playNextAudioChunk();
    }
}

function playNextAudioChunk() {
    if (isAudioPlaying || currentAudioQueue.length === 0) {
        return;
    }

    const blob = currentAudioQueue.shift();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    currentAudioElement = audio; // Store reference to the playing audio
    isAudioPlaying = true;
    // Status update happens when backend sends 'speaking' status type

    audio.onended = () => {
        console.log("Audio chunk ended.");
        isAudioPlaying = false;
        URL.revokeObjectURL(url); // Clean up the object URL
        currentAudioElement = null; // Clear reference
        // After a chunk ends, check if there are more chunks to play
        if (currentAudioQueue.length > 0) {
            playNextAudioChunk();
        } else {
            // If queue is empty, bot has finished speaking the response
            console.log("Finished playing all audio chunks for session:", currentVoiceSessionId);
            // Status is updated by backend sending 'ready' status after response
            currentVoiceSessionId = null; // Clear session ID after response is played
        }
    };

    audio.onerror = (e) => {
        console.error("Audio playback error:", e);
        isAudioPlaying = false;
        URL.revokeObjectURL(url);
        currentAudioElement = null;
        updateVoiceStatus("Playback Error"); // Show playback error status

        // Attempt to play next chunk even if this one failed
        if (currentAudioQueue.length > 0) {
            playNextAudioChunk();
        } else {
             // If no more chunks, status is updated by backend sending 'ready' after response
             currentVoiceSessionId = null;
        }
    };

    // Start playback
    audio.play().catch(e => {
        console.error("Audio play() failed:", e);
        // Catch promise rejection (e.g., user hasn't interacted yet or browser blocked autoplay)
        isAudioPlaying = false;
        URL.revokeObjectURL(url);
        currentAudioElement = null;
        updateVoiceStatus("Playback Blocked"); // Inform user playback was blocked
         // Attempt to play next chunk, but also inform user if needed
         if (currentAudioQueue.length > 0) {
             playNextAudioChunk();
         } else {
              // If no more chunks, status is updated by backend sending 'ready' after response
              currentVoiceSessionId = null;
         }
    });
}

// --- Stop Currently Playing Audio ---
function stopAudioPlayback() {
    if (currentAudioElement) {
        try {
            currentAudioElement.pause();
            currentAudioElement.currentTime = 0; // Reset time
            console.log("Audio playback stopped.");
             // Revoke URL and clear element immediately on explicit stop
             // This might be better than waiting for onended/onerror for manual stops
             try { URL.revokeObjectURL(currentAudioElement.src); } catch(e) { console.warn("Error revoking URL on stop:", e); }
             currentAudioElement = null;
        } catch (e) {
            console.warn("Error pausing audio:", e);
        } finally {
            isAudioPlaying = false;
        }
    }
     // Also clear the queue and reset state if stopping playback explicitly
     currentAudioQueue.length = 0;
     isAudioPlaying = false; // Redundant but safe
     // Status update depends on whether STT is listening or WS is open after stop
     if (speechRecognition && speechRecognition.recognizing) {
          updateVoiceStatus("Listening...");
     } else if (voiceSocket && voiceSocket.readyState === WebSocket.OPEN) {
          updateVoiceStatus("Connected. Click Start.");
     } else {
          updateVoiceStatus("Disconnected");
     }
}