const recipeData = {
    title: "咖哩飯",
    ingredients: [
        "洋蔥 1 顆",
        "馬鈴薯 2 顆",
        "胡蘿蔔 1 根",
        "咖哩塊 4 塊",
        "雞肉 300g"
    ],
    steps: [
        { step: 1, title: "準備食材", instruction: "切洋蔥、馬鈴薯和胡蘿蔔。", duration: 5 },
        { step: 2, title: "炒香食材", instruction: "加熱鍋子，放入洋蔥炒至透明。", duration: 4 },
        { step: 3, title: "加入咖哩", instruction: "加入咖哩塊和水煮滾，轉小火燉煮。", duration: 15 }
    ]
};

const state = {
    currentStep: 1
};

const elements = {
    progressList: document.getElementById("progressList"),
    projectionTitle: document.getElementById("projectionTitle"),
    projectionStep: document.getElementById("projectionStep"),
    projectionInstruction: document.getElementById("projectionInstruction"),
    projectionTimer: document.getElementById("projectionTimer"),
    projectionFill: document.getElementById("projectionFill"),
    prevNav: document.getElementById("prevNav"),
    nextNav: document.getElementById("nextNav")
};

function renderProgress() {
    elements.progressList.innerHTML = "";
    recipeData.steps.forEach((step) => {
        const item = document.createElement("div");
        item.className = "progress-step";
        item.innerHTML = `<strong>Step ${step.step}</strong><p>${step.title}</p>`;
        item.addEventListener("click", () => {
            state.currentStep = step.step;
            renderProjection();
        });
        elements.progressList.appendChild(item);
    });
}

function renderProjection() {
    const current = recipeData.steps.find((s) => s.step === state.currentStep);
    const total = recipeData.steps.length;
    const elapsed = recipeData.steps
        .filter((s) => s.step < state.currentStep)
        .reduce((sum, s) => sum + s.duration, 0);
    const remaining = recipeData.steps
        .filter((s) => s.step >= state.currentStep)
        .reduce((sum, s) => sum + s.duration, 0);

    elements.projectionTitle.textContent = recipeData.title;
    elements.projectionStep.textContent = `Step ${current.step} / ${total}`;
    elements.projectionInstruction.textContent = current.instruction;
    elements.projectionTimer.textContent = remaining;
    elements.projectionFill.style.width = `${Math.round((state.currentStep / total) * 100)}%`;
}


function handleNavigation(delta) {
    state.currentStep = Math.min(Math.max(state.currentStep + delta, 1), recipeData.steps.length);
    renderProjection();
}

function init() {
    renderProgress();
    renderProjection();

    elements.prevNav.addEventListener("click", () => handleNavigation(-1));
    elements.nextNav.addEventListener("click", () => handleNavigation(1));
}

init();
