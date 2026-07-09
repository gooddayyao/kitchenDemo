const CALIBRATION_KEY = "kitchen_projection_calibration";

class CalibrationManager {
    constructor() {
        this.corners = [];
        // Homography matrix mapping normalized [0..1] coordinates to screen pixels.
        // Computed from 4 calibration corners in the expected order:
        // 1: top-left, 2: top-right, 3: bottom-right, 4: bottom-left.
        this.homography = null; // { h11,h12,h13,h21,h22,h23,h31,h32 }
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

        if (this.corners?.length === 4) {
            this._computeHomography();
        }
    }

    startCalibration() {
        this.corners = [];
        this.homography = null;
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
        this.homography = null;
        this.isCalibrating = false;
        localStorage.removeItem(CALIBRATION_KEY);
        if (this.onUpdate) this.onUpdate(this);
    }

    isReady() {
        return this.corners.length === 4;
    }

    _computeHomography() {
        // Use normalized source rectangle corners:
        // (0,0)->tl, (1,0)->tr, (1,1)->br, (0,1)->bl.
        const [tl, tr, br, bl] = this.corners;
        if (!tl || !tr || !br || !bl) return;

        const src = [
            { x: 0, y: 0, X: tl.x, Y: tl.y },
            { x: 1, y: 0, X: tr.x, Y: tr.y },
            { x: 1, y: 1, X: br.x, Y: br.y },
            { x: 0, y: 1, X: bl.x, Y: bl.y },
        ];

        // Solve for 8 unknowns with h33 = 1:
        // [h11 h12 h13 h21 h22 h23 h31 h32]
        // X = (h11*x + h12*y + h13) / (h31*x + h32*y + 1)
        // Y = (h21*x + h22*y + h23) / (h31*x + h32*y + 1)
        const A = [];
        const b = [];
        for (const p of src) {
            const { x, y, X, Y } = p;
            // First row for X
            A.push([x, y, 1, 0, 0, 0, -X * x, -X * y]);
            b.push(X);
            // Second row for Y
            A.push([0, 0, 0, x, y, 1, -Y * x, -Y * y]);
            b.push(Y);
        }

        const x = this._solveLinearSystem(A, b);
        if (!x) return;
        const [h11, h12, h13, h21, h22, h23, h31, h32] = x;
        this.homography = { h11, h12, h13, h21, h22, h23, h31, h32 };
    }

    _solveLinearSystem(A, b) {
        // Gaussian elimination with partial pivoting for square matrix.
        // A: n x n, b: n
        const n = b.length;
        const M = new Array(n);
        for (let i = 0; i < n; i++) {
            M[i] = A[i].slice();
            M[i].push(b[i]);
        }

        for (let col = 0; col < n; col++) {
            // Find pivot row
            let pivotRow = col;
            let pivotVal = Math.abs(M[pivotRow][col]);
            for (let r = col + 1; r < n; r++) {
                const v = Math.abs(M[r][col]);
                if (v > pivotVal) {
                    pivotVal = v;
                    pivotRow = r;
                }
            }

            if (pivotVal < 1e-12) return null;

            // Swap
            if (pivotRow !== col) {
                const tmp = M[col];
                M[col] = M[pivotRow];
                M[pivotRow] = tmp;
            }

            // Normalize pivot row
            const div = M[col][col];
            for (let c = col; c <= n; c++) {
                M[col][c] /= div;
            }

            // Eliminate other rows
            for (let r = 0; r < n; r++) {
                if (r === col) continue;
                const factor = M[r][col];
                if (Math.abs(factor) < 1e-15) continue;
                for (let c = col; c <= n; c++) {
                    M[r][c] -= factor * M[col][c];
                }
            }
        }

        // Extract solution
        const out = new Array(n);
        for (let i = 0; i < n; i++) out[i] = M[i][n];
        return out;
    }

    /** Map normalized counter coords (0-1) to screen pixels */
    mapPoint(nx, ny, width, height) {
        if (!this.isReady()) {
            return { x: nx * width, y: ny * height };
        }

        // Homography mapping (projective transform).
        if (!this.homography) this._computeHomography();
        if (!this.homography) {
            // Fallback to previous bilinear approximation if homography fails.
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

        const { h11, h12, h13, h21, h22, h23, h31, h32 } = this.homography;
        const x = nx;
        const y = ny;
        const denom = h31 * x + h32 * y + 1;
        if (Math.abs(denom) < 1e-9) {
            return { x: nx * width, y: ny * height };
        }

        const X = (h11 * x + h12 * y + h13) / denom;
        const Y = (h21 * x + h22 * y + h23) / denom;
        return { x: X, y: Y };
    }

    mapZone(zone, width, height) {
        // Project all four corners and return an axis-aligned bounding box for existing overlay rendering.
        const x0 = zone.x;
        const y0 = zone.y;
        const x1 = zone.x + zone.w;
        const y1 = zone.y + zone.h;

        const pTL = this.mapPoint(x0, y0, width, height);
        const pTR = this.mapPoint(x1, y0, width, height);
        const pBR = this.mapPoint(x1, y1, width, height);
        const pBL = this.mapPoint(x0, y1, width, height);

        const minX = Math.min(pTL.x, pTR.x, pBR.x, pBL.x);
        const minY = Math.min(pTL.y, pTR.y, pBR.y, pBL.y);
        const maxX = Math.max(pTL.x, pTR.x, pBR.x, pBL.x);
        const maxY = Math.max(pTL.y, pTR.y, pBR.y, pBL.y);

        return {
            x: minX,
            y: minY,
            w: maxX - minX,
            h: maxY - minY,
        };
    }
}

window.CalibrationManager = CalibrationManager;
