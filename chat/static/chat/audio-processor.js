// audio-processor.js (with expanded debug logs)

// Define a version or timestamp to check for cache
const PROCESSOR_VERSION = '2025-05-06_1605'; // <--- UPDATE THIS TIMESTAMP WITH EACH CHANGE

// This class defines the custom AudioWorklet processor.
class AudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        console.log(`AudioProcessor constructed. Version: ${PROCESSOR_VERSION}`);

        this.outputBufferSize = 4096;
        this.accumulatedBuffer = new Float32Array(this.outputBufferSize);
        this.bufferIndex = 0;

         // Log port availability
         console.log(`[V${PROCESSOR_VERSION}] AudioProcessor constructor: port available? ${!!this.port}`);
    }

    // The process method is called automatically by the browser's audio rendering thread.
    process(inputs, outputs, parameters) {
        // Log at the very start of the process method - This will be VERY noisy, only uncomment temporarily if needed
        // console.log(`[V${PROCESSOR_VERSION}] Process method called. CurrentTime: ${currentTime.toFixed(3)}s`);

        // Log inputs/outputs structure on the first few calls or occasionally
        if (currentTime < 0.5) { // Log during the initial phase (first half second)
             console.log(`[V${PROCESSOR_VERSION}] Initial Process Call Debug:`);
             console.log(`[V${PROCESSOR_VERSION}] Inputs structure:`, inputs);
             console.log(`[V${PROCESSOR_VERSION}] Outputs structure:`, outputs);
             if (inputs && inputs.length > 0) {
                 console.log(`[V${PROCESSOR_VERSION}] Input[0] is Array:`, Array.isArray(inputs[0])); // Should be true
                 if (inputs[0] && inputs[0].length > 0) {
                      console.log(`[V${PROCESSOR_VERSION}] Input[0][0] instance of Float32Array:`, inputs[0][0] instanceof Float32Array); // Should be true
                      console.log(`[V${PROCESSOR_VERSION}] Input[0][0] length:`, inputs[0][0].length); // Should be 128 (worklet frame size)
                 }
             }
             if (outputs && outputs.length > 0) {
                  console.log(`[V${PROCESSOR_VERSION}] Output[0] is Array:`, Array.isArray(outputs[0])); // Should be true
                  console.log(`[V${PROCESSOR_VERSION}] Output[0] instance of Float32Array:`, outputs[0] instanceof Float32Array); // <-- THIS IS WHAT WE NEED TO BE TRUE
                  if (outputs[0]) {
                      console.log(`[V${PROCESSOR_VERSION}] Output[0] length:`, outputs[0].length); // Should be 128
                  }
             }
        }


        const input = inputs[0]; // Get the first input (assuming mono or first channel)
        if (!input || input.length === 0) {
            // console.log(`[V${PROCESSOR_VERSION}] Process: No input data.`); // Keep noisy logs commented
            return true; // Keep the processor alive even if no input
        }

        const inputChannelData = input[0]; // Get data from the first channel of the first input
        // console.log(`[V${PROCESSOR_VERSION}] Process: Got input channel data (length: ${inputChannelData.length}).`); // Keep noisy logs commented


        // Accumulate audio data into our buffer
        // Copy samples from the input buffer (inputChannelData) to our internal buffer (this.accumulatedBuffer)
        let inputReadIndex = 0; // Where we are reading from the current inputChannelData
        while (inputReadIndex < inputChannelData.length && this.bufferIndex < this.outputBufferSize) {
             const samplesToCopyInChunk = Math.min(inputChannelData.length - inputReadIndex, this.outputBufferSize - this.bufferIndex);
             this.accumulatedBuffer.set(inputChannelData.subarray(inputReadIndex, inputReadIndex + samplesToCopyInChunk), this.bufferIndex);
             this.bufferIndex += samplesToCopyInChunk;
             inputReadIndex += samplesToCopyInChunk;
        }

         // console.log(`[V${PROCESSOR_VERSION}] Process: Buffer index: ${this.bufferIndex}/${this.outputBufferSize}`); // Keep noisy logs commented


        // If the accumulated buffer is full, process and send it to the main thread
        if (this.bufferIndex === this.outputBufferSize) {
            console.log(`[V${PROCESSOR_VERSION}] Accumulated buffer full (${this.outputBufferSize} samples). Posting message to main thread.`); // <-- ADD THIS LOG

            // Calculate RMS for VAD (Voice Activity Detection) and send back to the main thread
            let sumOfSquares = 0;
            for (let i = 0; i < this.accumulatedBuffer.length; i++) {
                sumOfSquares += this.accumulatedBuffer[i] * this.accumulatedBuffer[i];
            }
            let rms = Math.sqrt(sumOfSquares / this.accumulatedBuffer.length);

            // Send RMS and the accumulated audio data back to the main thread
            // Use transfer ownership for efficiency when sending the buffer
            try {
                 this.port.postMessage({ type: 'vad_rms', rms: rms });
                  // Create a new buffer for the transfer to avoid issues with the original buffer lifecycle
                 const bufferToSend = this.accumulatedBuffer.slice().buffer; // Create a copy and get its ArrayBuffer
                 this.port.postMessage({ type: 'audio_data', buffer: bufferToSend }, [bufferToSend]);
                 console.log(`[V${PROCESSOR_VERSION}] Posted 'vad_rms' and 'audio_data' messages to main thread.`); // <-- ADD THIS LOG
            } catch (e) {
                 console.error(`[V${PROCESSOR_VERSION}] Error posting message to main thread:`, e);
                 this.port.postMessage({ type: 'processor_error', message: 'Error posting audio data to main thread', error: e.message });
            }


            // Create a new buffer for the next chunk
            this.accumulatedBuffer = new Float32Array(this.outputBufferSize);
            this.bufferIndex = 0;

             // Handle any leftover samples from the current input frame that didn't fit in the last buffer
             if (inputReadIndex < inputChannelData.length) {
                 const leftoverSamples = inputChannelData.length - inputReadIndex;
                 // console.log(`[V${PROCESSOR_VERSION}] Handling ${leftoverSamples} leftover samples.`); // Keep noisy logs commented
                 this.accumulatedBuffer.set(inputChannelData.subarray(inputReadIndex, inputReadIndex + leftoverSamples), this.bufferIndex);
                 this.bufferIndex += leftoverSamples;
             }
        }

        // To silence the output and prevent microphone loopback:
        // Explicitly access and zero out the first output channel.
        // The debug logs for this section are already in the previous version.
        if (outputs && outputs.length > 0 && outputs[0] instanceof Float32Array) {
             const outputChannelData = outputs[0];
             // console.log(`[V${PROCESSOR_VERSION}] Zeroing output buffer. Channel length: ${outputChannelData.length}`); // Keep noisy logs commented
             try {
                 for (let i = 0; i < outputChannelData.length; ++i) {
                     outputChannelData[i] = 0; // Manually set each sample to 0
                 }
                 // console.log(`[V${PROCESSOR_VERSION}] Output buffer zeroing successful.`); // Keep noisy logs commented
             } catch (e) {
                 console.error(`[V${PROCESSOR_VERSION}] Error during output zeroing:`, e); // Keep this log
                 this.port.postMessage({ type: 'processor_error', message: 'Error zeroing output buffer', error: e.message }); // Keep this post
             }
        } else {
            // These logs indicate outputs[0] is not a Float32Array as expected
            console.warn(`[V${PROCESSOR_VERSION}] AudioWorklet: Unexpected or empty outputs structure in process method. Skipping output zeroing.`); // Keep this log
            console.log(`[V${PROCESSOR_VERSION}] Outputs structure:`, outputs); // Keep this log
             if (outputs && outputs.length > 0) {
                  console.log(`[V${PROCESSOR_VERSION}] outputs[0] type:`, typeof outputs[0]); // <-- ADD THIS LOG
                  console.log(`[V${PROCESSOR_VERSION}] outputs[0] constructor name:`, outputs[0] ? outputs[0].constructor.name : 'N/A'); // <-- ADD THIS LOG
             }

        }


        // Return true to indicate that the processor should keep running.
        return true;
    }
}

// Register the processor with the AudioWorklet system.
registerProcessor('audio-processor', AudioProcessor);

console.log(`AudioProcessor registered. Version: ${PROCESSOR_VERSION}`); // Keep this log