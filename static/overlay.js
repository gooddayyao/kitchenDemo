class SpatialOverlay {
    constructor(canvas, calibration) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.calibration = calibration;
    }

    resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    clear() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    render({ recipe, step, timerRemaining, confirmMessage, showZones }) {
        this.clear();
        const w = this.canvas.width;
        const h = this.canvas.height;

        if (this.calibration.isCalibrating) {
            this._drawCalibrationUI(w, h);
            return;
        }

        if (!recipe || !step) return;

        if (showZones && recipe.zones) {
            Object.entries(recipe.zones).forEach(([key, zone]) => {
                const rect = this.calibration.mapZone(zone, w, h);
                const isActive = step.zone === key;
                this.ctx.strokeStyle = isActive ? "rgba(255, 209, 102, 0.9)" : "rgba(255,255,255,0.25)";
                this.ctx.lineWidth = isActive ? 3 : 1;
                this.ctx.strokeRect(rect.x, rect.y, rect.w, rect.h);
                this.ctx.fillStyle = isActive ? "rgba(255, 209, 102, 0.12)" : "rgba(255,255,255,0.04)";
                this.ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
                this.ctx.fillStyle = isActive ? "#ffd166" : "#aaa";
                this.ctx.font = "bold 18px Segoe UI, sans-serif";
                this.ctx.fillText(zone.label, rect.x + 8, rect.y + 24);
            });
        }

        const zone = recipe.zones?.[step.zone];
        if (zone) {
            const rect = this.calibration.mapZone(zone, w, h);

            if (step.guidance_type === "cut_lines" && step.guide_lines) {
                this._drawGuideLines(rect, step.guide_lines);
            }

            this._drawZoneHint(rect, step.instruction);

            if (step.timer_seconds > 0 && timerRemaining >= 0) {
                this._drawTimer(rect, timerRemaining);
            }
        }

        if (confirmMessage) {
            this._drawConfirmBanner(w, h, confirmMessage);
        }
    }

    _drawCalibrationUI(w, h) {
        this.ctx.fillStyle = "rgba(0,0,0,0.55)";
        this.ctx.fillRect(0, 0, w, h);
        this.ctx.fillStyle = "#fff";
        this.ctx.font = "24px Segoe UI, sans-serif";
        this.ctx.fillText(
            `點選料理台四角進行校正 (${this.calibration.corners.length}/4)`,
            w / 2 - 200,
            60
        );
        this.calibration.corners.forEach((c, i) => {
            this.ctx.beginPath();
            this.ctx.arc(c.x, c.y, 10, 0, Math.PI * 2);
            this.ctx.fillStyle = "#4db6ac";
            this.ctx.fill();
            this.ctx.fillStyle = "#fff";
            this.ctx.font = "14px Segoe UI";
            this.ctx.fillText(String(i + 1), c.x - 4, c.y + 5);
        });
    }

    _drawGuideLines(rect, guide) {
        const { orientation, spacing_px, count, label } = guide;
        this.ctx.strokeStyle = "rgba(100, 220, 255, 0.85)";
        this.ctx.lineWidth = 2;
        this.ctx.setLineDash([12, 8]);

        if (orientation === "vertical" || orientation === "grid") {
            const spacing = spacing_px || 48;
            for (let i = 1; i <= (count || 5); i++) {
                const x = rect.x + i * spacing;
                if (x > rect.x + rect.w) break;
                this.ctx.beginPath();
                this.ctx.moveTo(x, rect.y + 10);
                this.ctx.lineTo(x, rect.y + rect.h - 10);
                this.ctx.stroke();
            }
        }
        if (orientation === "horizontal" || orientation === "grid") {
            const spacing = spacing_px || 36;
            for (let i = 1; i <= (count || 4); i++) {
                const y = rect.y + i * spacing;
                if (y > rect.y + rect.h) break;
                this.ctx.beginPath();
                this.ctx.moveTo(rect.x + 10, y);
                this.ctx.lineTo(rect.x + rect.w - 10, y);
                this.ctx.stroke();
            }
        }
        this.ctx.setLineDash([]);

        if (label) {
            this.ctx.fillStyle = "rgba(100, 220, 255, 0.95)";
            this.ctx.font = "bold 20px Segoe UI, sans-serif";
            this.ctx.fillText(label, rect.x + 12, rect.y + rect.h - 16);
        }
    }

    _drawZoneHint(rect, instruction) {
        const maxWidth = rect.w - 24;
        this.ctx.fillStyle = "rgba(20, 20, 25, 0.82)";
        const lines = this._wrapText(instruction, maxWidth, "18px Segoe UI");
        const boxH = lines.length * 24 + 24;
        const boxY = rect.y + 36;
        this.ctx.fillRect(rect.x + 8, boxY, rect.w - 16, boxH);
        this.ctx.fillStyle = "#f3f3f3";
        this.ctx.font = "18px Segoe UI, sans-serif";
        lines.forEach((line, i) => {
            this.ctx.fillText(line, rect.x + 20, boxY + 28 + i * 24);
        });
    }

    _drawTimer(rect, seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        const text = `${mins}:${secs.toString().padStart(2, "0")}`;
        this.ctx.fillStyle = "rgba(255, 100, 80, 0.92)";
        this.ctx.beginPath();
        this.ctx.arc(rect.x + rect.w - 50, rect.y + 50, 40, 0, Math.PI * 2);
        this.ctx.fill();
        this.ctx.fillStyle = "#fff";
        this.ctx.font = "bold 22px Segoe UI, sans-serif";
        this.ctx.textAlign = "center";
        this.ctx.fillText(text, rect.x + rect.w - 50, rect.y + 58);
        this.ctx.textAlign = "start";
    }

    _drawConfirmBanner(w, h, message) {
        const boxW = Math.min(600, w - 80);
        const x = (w - boxW) / 2;
        const y = h - 120;
        this.ctx.fillStyle = "rgba(255, 140, 60, 0.92)";
        this.ctx.fillRect(x, y, boxW, 70);
        this.ctx.fillStyle = "#fff";
        this.ctx.font = "bold 20px Segoe UI, sans-serif";
        this.ctx.textAlign = "center";
        this.ctx.fillText(message, x + boxW / 2, y + 42);
        this.ctx.textAlign = "start";
    }

    _wrapText(text, maxWidth, font) {
        this.ctx.font = font;
        const words = text.split("");
        const lines = [];
        let line = "";
        for (const ch of words) {
            const test = line + ch;
            if (this.ctx.measureText(test).width > maxWidth && line) {
                lines.push(line);
                line = ch;
            } else {
                line = test;
            }
        }
        if (line) lines.push(line);
        return lines.slice(0, 4);
    }
}

window.SpatialOverlay = SpatialOverlay;
