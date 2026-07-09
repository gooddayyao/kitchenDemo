const STEP_STATUS = {
    PENDING: "pending",
    ACTIVE: "active",
    AWAITING_CONFIRM: "awaiting_confirm",
    DONE: "done",
};

class StepEngine {
    constructor() {
        this.recipe = null;
        this.stepStatuses = {};
        this.currentStep = 1;
        this.timerInterval = null;
        this.timerRemaining = 0;
        this.onChange = null;
        this.onTimerTick = null;
        this.onAwaitingConfirm = null;
    }

    loadRecipe(recipe) {
        this.recipe = recipe;
        this.stepStatuses = {};
        recipe.steps.forEach((step) => {
            this.stepStatuses[step.step] = STEP_STATUS.PENDING;
        });
        this.currentStep = 1;
        this._activateStep(1);
        this._notify();
    }

    getCurrentStep() {
        if (!this.recipe) return null;
        return this.recipe.steps.find((s) => s.step === this.currentStep) || null;
    }

    getStepStatus(stepNum) {
        return this.stepStatuses[stepNum] || STEP_STATUS.PENDING;
    }

    _activateStep(stepNum) {
        this._stopTimer();
        this.currentStep = stepNum;
        this.stepStatuses[stepNum] = STEP_STATUS.ACTIVE;

        const step = this.getCurrentStep();
        if (step && step.timer_seconds > 0) {
            this.timerRemaining = step.timer_seconds;
            this._startTimer(step);
        } else {
            this.timerRemaining = 0;
        }
        this._notify();
    }

    _startTimer(step) {
        this._stopTimer();
        this.timerInterval = setInterval(() => {
            this.timerRemaining -= 1;
            if (this.onTimerTick) this.onTimerTick(this.timerRemaining, step);
            if (this.timerRemaining <= 0) {
                this.timerRemaining = 0;
                this._stopTimer();
                this._handleCompletion(step, true);
            }
        }, 1000);
    }

    _stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    /**
     * Timer end behavior:
     * - completion === "timer" → auto-advance
     * - otherwise → awaiting_confirm (manual / vision assisted)
     */
    _handleCompletion(step, fromTimer = false) {
        if (fromTimer && step.completion === "timer") {
            this._completeStep(step.step);
            return;
        }
        this.stepStatuses[step.step] = STEP_STATUS.AWAITING_CONFIRM;
        if (this.onAwaitingConfirm) {
            this.onAwaitingConfirm(
                step,
                fromTimer
                    ? `計時結束，請確認「${step.title}」是否完成`
                    : `請確認「${step.title}」是否完成`
            );
        }
        this._notify();
    }

    /**
     * Conservative vision handling:
     * - high confidence + detected → auto-complete for vision/marker steps
     * - uncertain → prompt confirm without leaving ACTIVE (keep polling / avoid false advance)
     */
    applyVisionResult(result) {
        const step = this.getCurrentStep();
        const status = step ? this.getStepStatus(step.step) : null;
        if (!step || (status !== STEP_STATUS.ACTIVE && status !== STEP_STATUS.AWAITING_CONFIRM)) {
            return;
        }

        const canAuto =
            step.completion === "vision_heuristic" || step.completion === "marker_detect";
        const highConfidence = result.confidence >= 0.6 && result.detected && !result.needs_confirm;

        if (canAuto && highConfidence && status === STEP_STATUS.ACTIVE) {
            this._completeStep(step.step);
            return;
        }

        if (result.needs_confirm || !highConfidence) {
            if (this.onAwaitingConfirm) {
                this.onAwaitingConfirm(
                    step,
                    result.message || `狀態不明確，請確認「${step.title}」是否完成`
                );
            }
            // Stay ACTIVE so polling can recover; UI shows confirm from message + completion type.
            this._notify();
        }
    }

    confirmCurrentStep() {
        const step = this.getCurrentStep();
        if (!step) return;
        const status = this.getStepStatus(step.step);
        if (status !== STEP_STATUS.ACTIVE && status !== STEP_STATUS.AWAITING_CONFIRM) return;
        this._completeStep(step.step);
    }

    _completeStep(stepNum) {
        this._stopTimer();
        this.stepStatuses[stepNum] = STEP_STATUS.DONE;
        const next = this.recipe.steps.find((s) => s.step === stepNum + 1);
        if (next) {
            this._activateStep(next.step);
        } else {
            this.currentStep = stepNum;
            this._notify();
        }
    }

    goToStep(stepNum) {
        if (!this.recipe) return;
        const step = this.recipe.steps.find((s) => s.step === stepNum);
        if (!step) return;
        this.recipe.steps.forEach((s) => {
            if (s.step < stepNum) this.stepStatuses[s.step] = STEP_STATUS.DONE;
            else if (s.step > stepNum) this.stepStatuses[s.step] = STEP_STATUS.PENDING;
        });
        this._activateStep(stepNum);
    }

    nextStep() {
        if (!this.recipe) return;
        const idx = this.recipe.steps.findIndex((s) => s.step === this.currentStep);
        if (idx < this.recipe.steps.length - 1) {
            this.stepStatuses[this.currentStep] = STEP_STATUS.DONE;
            this._activateStep(this.recipe.steps[idx + 1].step);
        }
    }

    prevStep() {
        if (!this.recipe) return;
        const idx = this.recipe.steps.findIndex((s) => s.step === this.currentStep);
        if (idx > 0) {
            this._activateStep(this.recipe.steps[idx - 1].step);
        }
    }

    isRecipeComplete() {
        if (!this.recipe) return false;
        return this.recipe.steps.every((s) => this.stepStatuses[s.step] === STEP_STATUS.DONE);
    }

    _notify() {
        if (this.onChange) this.onChange(this);
    }

    destroy() {
        this._stopTimer();
    }
}

window.StepEngine = StepEngine;
window.STEP_STATUS = STEP_STATUS;
