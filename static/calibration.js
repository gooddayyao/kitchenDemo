const CALIBRATION_KEY = "kitchen_projection_calibration";

class CalibrationManager {
    constructor() {
        this.corners = [];
        this.isCalibrating = false;
        this.onUpdate = null;
    }

    async load() {
        try {
            const res = await fetch("/api/calibration");
            if (res.ok) {
                const data = await res.json();
                if (data.corners?.length === 4) {
                    this.corners = data.corners;
                    return;
                }
            }
        } catch (_) { /* use localStorage fallback */ }

        const stored = localStorage.getItem(CALIBRATION_KEY);
        if (stored) {
            const data = JSON.parse(stored);
            this.corners = data.corners || [];
        }
    }

    startCalibration() {
        this.corners = [];
        this.isCalibrating = true;
        if (this.onUpdate) this.onUpdate(this);
    }

    addCorner(x, y) {
        if (!this.isCalibrating || this.corners.length >= 4) return;
        this.corners.push({ x, y });
        if (this.corners.length === 4) {
            this.isCalibrating = false;
            this.save();
        }
        if (this.onUpdate) this.onUpdate(this);
    }

    async save() {
        const payload = { corners: this.corners, zones: null };
        localStorage.setItem(CALIBRATION_KEY, JSON.stringify(payload));
        try {
            await fetch("/api/calibration", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
        } catch (_) { /* localStorage is sufficient */ }
    }

    reset() {
        this.corners = [];
        this.isCalibrating = false;
        localStorage.removeItem(CALIBRATION_KEY);
        if (this.onUpdate) this.onUpdate(this);
    }

    isReady() {
        return this.corners.length === 4;
    }

    /** Map normalized counter coords (0-1) to screen pixels */
    mapPoint(nx, ny, width, height) {
        if (!this.isReady()) {
            return { x: nx * width, y: ny * height };
        }
        const [tl, tr, br, bl] = this.corners;
        const top = {
            x: tl.x + (tr.x - tl.x) * nx,
            y: tl.y + (tr.y - tl.y) * nx,
        };
        const bottom = {
            x: bl.x + (br.x - bl.x) * nx,
            y: bl.y + (br.y - bl.y) * nx,
        };
        return {
            x: top.x + (bottom.x - top.x) * ny,
            y: top.y + (bottom.y - top.y) * ny,
        };
    }

    mapZone(zone, width, height) {
        const tl = this.mapPoint(zone.x, zone.y, width, height);
        const br = this.mapPoint(zone.x + zone.w, zone.y + zone.h, width, height);
        return {
            x: tl.x,
            y: tl.y,
            w: br.x - tl.x,
            h: br.y - tl.y,
        };
    }
}

window.CalibrationManager = CalibrationManager;
