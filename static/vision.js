class VisionMonitor {
    constructor() {
        this.video = null;
        this.canvas = null;
        this.ctx = null;
        this.stream = null;
        this.interval = null;
        this.prevFrame = null;
        this.motionScore = 0;
        this.onResult = null;
        this.enabled = false;
        this.stepContext = null;
    }

    async init(videoEl, canvasEl) {
        this.video = videoEl;
        this.canvas = canvasEl;
        this.ctx = canvasEl.getContext("2d", { willReadFrequently: true });
    }

    async start() {
        if (this.stream) return;
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "environment", width: 320, height: 240 },
            });
            this.video.srcObject = this.stream;
            await this.video.play();
            this.enabled = true;
        } catch (err) {
            console.warn("Camera unavailable:", err);
            this.enabled = false;
        }
    }

    stop() {
        this.stopPolling();
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
        this.enabled = false;
    }

    setStepContext(step) {
        this.stepContext = step
            ? {
                  completion: step.completion,
                  zone: step.zone,
                  step: step.step,
                  title: step.title,
                  instruction: step.instruction,
                  motion_score: this.motionScore,
              }
            : null;
    }

    startPolling(intervalMs = 3000) {
        this.stopPolling();
        if (!this.enabled) return;
        this.interval = setInterval(() => this._analyze(), intervalMs);
    }

    stopPolling() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }

    _computeMotion(imageData) {
        const data = imageData.data;
        if (!this.prevFrame || this.prevFrame.length !== data.length) {
            this.prevFrame = new Uint8ClampedArray(data);
            return 0;
        }
        let diff = 0;
        const step = 16;
        for (let i = 0; i < data.length; i += 4 * step) {
            diff += Math.abs(data[i] - this.prevFrame[i]);
        }
        this.prevFrame = new Uint8ClampedArray(data);
        const samples = data.length / (4 * step);
        return diff / samples / 255;
    }

    async _analyze() {
        if (!this.enabled || !this.stepContext || !this.ctx) return;

        const needsVision = ["vision_heuristic", "marker_detect"].includes(
            this.stepContext.completion
        );
        if (!needsVision) return;

        this.canvas.width = this.video.videoWidth || 320;
        this.canvas.height = this.video.videoHeight || 240;
        this.ctx.drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
        const imageData = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
        this.motionScore = this._computeMotion(imageData);

        const imageB64 = this.canvas.toDataURL("image/jpeg", 0.6);
        const payload = {
            image: imageB64,
            step_context: { ...this.stepContext, motion_score: this.motionScore },
        };

        try {
            const res = await fetch("/api/vision/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            if (res.ok) {
                const result = await res.json();
                // Force conservative semantics for the step engine.
                if (result.confidence < 0.6) {
                    result.detected = false;
                    result.needs_confirm = true;
                }
                if (this.onResult) this.onResult(result);
            }
        } catch (err) {
            console.warn("Vision analyze failed:", err);
            if (this.onResult) {
                this.onResult({
                    detected: false,
                    confidence: 0,
                    needs_confirm: true,
                    message: "視覺分析失敗，請手動確認",
                    source: "none",
                });
            }
        }
    }
}

window.VisionMonitor = VisionMonitor;
