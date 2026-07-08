const engine = new StepEngine();
const calibration = new CalibrationManager();
let overlay = null;
const vision = new VisionMonitor();

const state = {
    recipe: null,
    isProjectionMode: false,
    confirmMessage: null,
    showZones: true,
    dragStartX: 0,
    dragStartY: 0,
    dragOffsetX: 0,
    dragOffsetY: 0,
    isDragging: false,
};

const elements = {
    controlPanel: document.getElementById("controlPanel"),
    recipeSelect: document.getElementById("recipeSelect"),
    recipeTitle: document.getElementById("recipeTitle"),
    recipeMeta: document.getElementById("recipeMeta"),
    progressList: document.getElementById("progressList"),
    projectionTitle: document.getElementById("projectionTitle"),
    projectionStep: document.getElementById("projectionStep"),
    projectionInstruction: document.getElementById("projectionInstruction"),
    projectionTimer: document.getElementById("projectionTimer"),
    projectionTimerWrap: document.getElementById("projectionTimerWrap"),
    projectionStatus: document.getElementById("projectionStatus"),
    projectionFill: document.getElementById("projectionFill"),
    prevNav: document.getElementById("prevNav"),
    nextNav: document.getElementById("nextNav"),
    confirmStep: document.getElementById("confirmStep"),
    projectButton: document.getElementById("projectButton"),
    calibrateButton: document.getElementById("calibrateButton"),
    recipeInput: document.getElementById("recipeInput"),
    parseRecipeBtn: document.getElementById("parseRecipeBtn"),
    ingredientList: document.getElementById("ingredientList"),

    projectionMode: document.getElementById("projectionMode"),
    projectionBg: document.getElementById("projectionBg"),
    spatialCanvas: document.getElementById("spatialCanvas"),
    projectionCardFullscreen: document.getElementById("projectionCardFullscreen"),
    projectionTitleFS: document.getElementById("projectionTitleFS"),
    projectionStepFS: document.getElementById("projectionStepFS"),
    projectionInstructionFS: document.getElementById("projectionInstructionFS"),
    projectionTimerFS: document.getElementById("projectionTimerFS"),
    projectionTimerWrapFS: document.getElementById("projectionTimerWrapFS"),
    prevNavFS: document.getElementById("prevNavFS"),
    nextNavFS: document.getElementById("nextNavFS"),
    confirmStepFS: document.getElementById("confirmStepFS"),
    exitProject: document.getElementById("exitProject"),
    bgSelect: document.getElementById("bgSelect"),
    showZones: document.getElementById("showZones"),
    cameraVideo: document.getElementById("cameraVideo"),
    cameraCanvas: document.getElementById("cameraCanvas"),
};

function formatTimer(seconds) {
    if (!seconds || seconds <= 0) return "不需計時";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, "0")}`;
}

function statusLabel(status) {
    const map = {
        pending: "待開始",
        active: "進行中",
        awaiting_confirm: "待確認",
        done: "已完成",
    };
    return map[status] || status;
}

async function fetchRecipes() {
    const res = await fetch("/api/recipes");
    const data = await res.json();
    elements.recipeSelect.innerHTML = "";
    data.recipes.forEach((r) => {
        const opt = document.createElement("option");
        opt.value = r.id;
        opt.textContent = `${r.title} (${r.step_count} 步)`;
        elements.recipeSelect.appendChild(opt);
    });
    return data.recipes;
}

async function loadRecipe(recipeId) {
    const res = await fetch(`/api/recipes/${recipeId}`);
    const recipe = await res.json();
    applyRecipe(recipe);
}

function applyRecipe(recipe) {
    state.recipe = recipe;
    engine.loadRecipe(recipe);
    renderAll();
}

function renderIngredients() {
    if (!state.recipe) return;
    elements.ingredientList.innerHTML = "";
    state.recipe.ingredients.forEach((ing) => {
        const li = document.createElement("li");
        li.textContent = ing.prep ? `${ing.name} ${ing.quantity} (${ing.prep})` : `${ing.name} ${ing.quantity}`;
        elements.ingredientList.appendChild(li);
    });
}

function renderProgress() {
    if (!state.recipe) return;
    elements.progressList.innerHTML = "";
    state.recipe.steps.forEach((step) => {
        const item = document.createElement("div");
        const st = engine.getStepStatus(step.step);
        item.className = `progress-step ${st}${step.step === engine.currentStep ? " current" : ""}`;
        item.innerHTML = `<strong>Step ${step.step}</strong><span class="step-status">${statusLabel(st)}</span><p>${step.title}</p>`;
        item.addEventListener("click", () => engine.goToStep(step.step));
        elements.progressList.appendChild(item);
    });
}

function renderProjection() {
    if (!state.recipe) return;
    const step = engine.getCurrentStep();
    const total = state.recipe.steps.length;
    const doneCount = state.recipe.steps.filter((s) => engine.getStepStatus(s.step) === STEP_STATUS.DONE).length;
    const timerText = formatTimer(engine.timerRemaining);
    const hasTimer = step && step.timer_seconds > 0;
    const stepStatus = step ? engine.getStepStatus(step.step) : "";

    const update = (titleEl, stepEl, instrEl, timerEl, timerWrapEl) => {
        titleEl.textContent = state.recipe.title;
        if (step) {
            stepEl.textContent = `Step ${step.step} / ${total} — ${step.title}`;
            instrEl.textContent = step.instruction;
            timerEl.textContent = timerText;
            timerWrapEl.style.display = hasTimer ? "block" : "none";
        }
    };

    update(
        elements.projectionTitle,
        elements.projectionStep,
        elements.projectionInstruction,
        elements.projectionTimer,
        elements.projectionTimerWrap
    );
    update(
        elements.projectionTitleFS,
        elements.projectionStepFS,
        elements.projectionInstructionFS,
        elements.projectionTimerFS,
        elements.projectionTimerWrapFS
    );

    elements.recipeTitle.textContent = state.recipe.title;
    elements.recipeMeta.textContent = `${total} 步驟`;
    elements.projectionStatus.textContent = step
        ? `狀態：${statusLabel(stepStatus)}${state.confirmMessage ? ` — ${state.confirmMessage}` : ""}`
        : "";
    elements.projectionFill.style.width = `${Math.round((doneCount / total) * 100)}%`;

    const showConfirm = stepStatus === STEP_STATUS.AWAITING_CONFIRM ||
        (step && step.completion === "manual_confirm" && stepStatus === STEP_STATUS.ACTIVE);
    elements.confirmStep.style.display = showConfirm ? "block" : "none";
    elements.confirmStepFS.style.display = showConfirm ? "block" : "none";

    renderSpatialOverlay();
    vision.setStepContext(step);
}

function renderSpatialOverlay() {
    if (!overlay) return;
    overlay.render({
        recipe: state.recipe,
        step: engine.getCurrentStep(),
        timerRemaining: engine.timerRemaining,
        confirmMessage: state.confirmMessage,
        showZones: state.showZones,
    });
}

function renderAll() {
    renderIngredients();
    renderProgress();
    renderProjection();
}

function enterProjectionMode() {
    state.isProjectionMode = true;
    elements.controlPanel.style.display = "none";
    elements.projectionMode.classList.add("active");
    updateProjectionBackground(elements.bgSelect.value || "dark");
    state.dragOffsetX = 0;
    state.dragOffsetY = 0;
    elements.projectionCardFullscreen.style.transform = "translate(0, 0)";
    overlay.resize();
    vision.start().then(() => vision.startPolling(3000));
    renderProjection();
}

function exitProjectionMode() {
    state.isProjectionMode = false;
    elements.projectionMode.classList.remove("active");
    elements.controlPanel.style.display = "grid";
    vision.stopPolling();
    vision.stop();
    calibration.isCalibrating = false;
    state.confirmMessage = null;
}

function updateProjectionBackground(bgClass) {
    elements.projectionBg.className = "projection-background " + bgClass;
}

function setupCardDragging() {
    const card = elements.projectionCardFullscreen;
    const onStart = (x, y) => {
        if (calibration.isCalibrating) return;
        state.isDragging = true;
        state.dragStartX = x - state.dragOffsetX;
        state.dragStartY = y - state.dragOffsetY;
        card.classList.add("dragging");
    };
    card.addEventListener("mousedown", (e) => onStart(e.clientX, e.clientY));
    document.addEventListener("mousemove", (e) => {
        if (!state.isDragging) return;
        state.dragOffsetX = e.clientX - state.dragStartX;
        state.dragOffsetY = e.clientY - state.dragStartY;
        card.style.transform = `translate(${state.dragOffsetX}px, ${state.dragOffsetY}px)`;
    });
    document.addEventListener("mouseup", () => {
        state.isDragging = false;
        card.classList.remove("dragging");
    });
}

function setupCalibrationClicks() {
    elements.spatialCanvas.addEventListener("click", (e) => {
        if (!state.isProjectionMode) return;
        if (calibration.isCalibrating) {
            calibration.addCorner(e.clientX, e.clientY);
            renderSpatialOverlay();
        }
    });
}

async function parseRecipeFromText() {
    const text = elements.recipeInput.value.trim();
    if (!text) return;
    const res = await fetch("/api/parse-recipe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
    });
    const recipe = await res.json();
    applyRecipe(recipe);
}

function bindEngine() {
    engine.onChange = () => {
        state.confirmMessage = null;
        renderAll();
    };
    engine.onTimerTick = () => renderProjection();
    engine.onAwaitingConfirm = (step, message) => {
        state.confirmMessage = message || `請確認「${step.title}」是否完成`;
        renderProjection();
    };
}

function bindVision() {
    vision.onResult = (result) => {
        if (result.needs_confirm && result.message) {
            state.confirmMessage = result.message;
        }
        engine.applyVisionResult(result);
    };
}

async function init() {
    overlay = new SpatialOverlay(elements.spatialCanvas, calibration);
    await calibration.load();
    calibration.onUpdate = () => renderSpatialOverlay();

    bindEngine();
    bindVision();
    setupCardDragging();
    setupCalibrationClicks();

    const recipes = await fetchRecipes();
    if (recipes.length) {
        await loadRecipe(recipes[0].id);
    }

    elements.recipeSelect.addEventListener("change", (e) => loadRecipe(e.target.value));
    elements.prevNav.addEventListener("click", () => engine.prevStep());
    elements.nextNav.addEventListener("click", () => engine.nextStep());
    elements.prevNavFS.addEventListener("click", () => engine.prevStep());
    elements.nextNavFS.addEventListener("click", () => engine.nextStep());
    elements.confirmStep.addEventListener("click", () => {
        state.confirmMessage = null;
        engine.confirmCurrentStep();
    });
    elements.confirmStepFS.addEventListener("click", () => {
        state.confirmMessage = null;
        engine.confirmCurrentStep();
    });
    elements.projectButton.addEventListener("click", enterProjectionMode);
    elements.exitProject.addEventListener("click", exitProjectionMode);
    elements.calibrateButton.addEventListener("click", () => {
        enterProjectionMode();
        calibration.startCalibration();
        renderSpatialOverlay();
    });
    elements.parseRecipeBtn.addEventListener("click", parseRecipeFromText);
    elements.bgSelect.addEventListener("change", (e) => updateProjectionBackground(e.target.value));
    elements.showZones.addEventListener("change", (e) => {
        state.showZones = e.target.checked;
        renderSpatialOverlay();
    });

    window.addEventListener("resize", () => {
        if (overlay) overlay.resize();
        renderSpatialOverlay();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && state.isProjectionMode) exitProjectionMode();
    });
}

init();
