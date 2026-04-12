/**
 * WDCalculator notes UI — state, render, and events for the notes cluster.
 * Relies on wdcalculator_scripts_config.html for wdNotesCategories and on shared.js for escapeHtml.
 * Globals notesList / notesCategories are shared with the inline calculator orchestration script.
 */
var notesList = [];
var notesCategories = typeof notesCategories !== "undefined" ? notesCategories : [];

function loadNotesCategories() {
    notesCategories = wdNotesCategories || [];
}

function setNoteMode(selectEl, textareaEl, mode) {
    if (mode === "select") {
        selectEl.style.setProperty("display", "block", "important");
        selectEl.classList.remove("d-none");
        textareaEl.style.setProperty("display", "none", "important");
        textareaEl.classList.add("d-none");
    } else {
        selectEl.style.setProperty("display", "none", "important");
        selectEl.classList.add("d-none");
        textareaEl.style.setProperty("display", "block", "important");
        textareaEl.classList.remove("d-none");
    }
}

function createNotesSelectOptions() {
    let optionsHtml = '<option value="">저장된 비고 선택</option>';
    if (notesCategories && Array.isArray(notesCategories)) {
        notesCategories.forEach((category) => {
            if (category && category.options && Array.isArray(category.options)) {
                category.options.forEach((option) => {
                    if (option && option.name) {
                        const value = `${category.name} > ${option.name}`;
                        const escapedValue = escapeHtml(value);
                        optionsHtml += `<option value="${escapedValue}">${escapedValue}</option>`;
                    }
                });
            }
        });
    }
    return optionsHtml;
}

function addNoteItem(type) {
    type = type || "select";
    var index = notesList.length;
    notesList.push({ type: type, value: "" });
    renderNoteItem(index);
}

function removeNoteItem(index) {
    if (notesList.length <= 1) {
        return;
    }
    notesList.splice(index, 1);
    renderAllNotes();
}

function toggleNoteType(index) {
    if (index >= 0 && index < notesList.length) {
        var currentType = notesList[index].type;
        var currentValue = notesList[index].value;
        notesList[index].type = currentType === "select" ? "input" : "select";
        notesList[index].value = currentValue;
        renderNoteItem(index);
    }
}

function renderNoteItem(index) {
    const container = document.getElementById("notesContainer");
    if (!container) return;

    const note = notesList[index];
    if (!note) return;

    const noteId = `note-item-${index}`;

    let noteItem = document.getElementById(noteId);
    if (noteItem) {
        noteItem.remove();
    }

    let optionValue = "";
    if (note.value && note.type === "select") {
        if (wdNotesCategories && Array.isArray(wdNotesCategories)) {
            for (const category of wdNotesCategories) {
                if (category && category.options && Array.isArray(category.options)) {
                    for (const option of category.options) {
                        if (option && option.name) {
                            const fullValue = `${category.name} > ${option.name}`;
                            if (fullValue === note.value) {
                                optionValue = fullValue;
                                break;
                            }
                        }
                    }
                    if (optionValue) break;
                }
            }
        }
    }

    let finalIsSelect = note.type === "select";
    if (finalIsSelect && note.value && !optionValue) {
        const isActuallyOption = checkIfOptionExists(note.value);
        if (!isActuallyOption) {
            notesList[index].type = "input";
            finalIsSelect = false;
        }
    }

    noteItem = document.createElement("div");
    noteItem.className = "note-item mb-2";
    noteItem.id = noteId;
    noteItem.setAttribute("data-note-index", index);

    noteItem.innerHTML = `
            <div class="d-flex gap-2 align-items-start">
                <button type="button" class="btn btn-sm btn-outline-secondary toggle-note-type" data-note-index="${index}" title="${finalIsSelect ? "직접입력" : "옵션 선택"}">
                    <i class="fas ${finalIsSelect ? "fa-keyboard" : "fa-list"}"></i>
                </button>
                <select class="form-select flex-grow-1 note-select" data-note-index="${index}">
                    ${createNotesSelectOptions()}
                </select>
                <textarea class="form-control note-input" rows="2" placeholder="비고를 직접 입력하세요" data-note-index="${index}"></textarea>
                <button type="button" class="btn btn-sm btn-outline-danger remove-note" data-note-index="${index}" title="삭제" ${notesList.length <= 1 ? "disabled" : ""}>
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;

    container.appendChild(noteItem);

    const select = noteItem.querySelector(".note-select");
    const textarea = noteItem.querySelector(".note-input");

    setNoteMode(select, textarea, finalIsSelect ? "select" : "input");

    if (finalIsSelect && select) {
        select.value = optionValue || "";
    } else if (textarea) {
        textarea.value = note.value || "";
    }

    attachNoteItemEvents(noteItem, index);
}

function attachNoteItemEvents(noteItem, index) {
    var toggleBtn = noteItem.querySelector(".toggle-note-type");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleNoteType(index);
        });
    }

    var removeBtn = noteItem.querySelector(".remove-note");
    if (removeBtn) {
        removeBtn.addEventListener("click", function (e) {
            e.preventDefault();
            e.stopPropagation();
            removeNoteItem(index);
        });
    }

    var select = noteItem.querySelector(".note-select");
    if (select) {
        select.addEventListener("change", function () {
            if (index >= 0 && index < notesList.length) {
                notesList[index].value = this.value;
                notesList[index].type = "select";
            }
        });
    }

    var textarea = noteItem.querySelector(".note-input");
    if (textarea) {
        textarea.addEventListener("input", function () {
            if (index >= 0 && index < notesList.length) {
                notesList[index].value = this.value;
                notesList[index].type = "input";
            }
        });

        textarea.addEventListener("blur", function () {
            var formatted = formatNumbersInText(this.value);
            if (formatted !== this.value) {
                this.value = formatted;
                if (index >= 0 && index < notesList.length) {
                    notesList[index].value = formatted;
                }
            }
        });
    }
}

function renderAllNotes() {
    var container = document.getElementById("notesContainer");
    if (!container) return;

    container.innerHTML = "";

    if (notesList.length === 0) {
        addNoteItem("select");
        return;
    }

    notesList.forEach(function (_note, index) {
        renderNoteItem(index);
    });
}

function collectNotes() {
    return notesList
        .map(function (item) {
            return item.value;
        })
        .filter(function (v) {
            return v && v.trim();
        })
        .join("\n");
}

function loadNotes(notesString) {
    if (!notesString || !notesString.trim()) {
        notesList = [{ type: "select", value: "" }];
        renderAllNotes();
        return;
    }

    if (!notesCategories || notesCategories.length === 0) {
        loadNotesCategories();
        if (!notesCategories || notesCategories.length === 0) {
            setTimeout(function () {
                loadNotesCategories();
                if (notesCategories && notesCategories.length > 0) {
                    loadNotes(notesString);
                }
            }, 100);
            return;
        }
    }

    var lines = notesString.split("\n").filter(function (v) {
        return v.trim();
    });

    if (lines.length === 0) {
        notesList = [{ type: "select", value: "" }];
        renderAllNotes();
        return;
    }

    notesList = lines.map(function (value) {
        value = value.trim();
        var isOption = checkIfOptionExists(value);
        return {
            type: isOption ? "select" : "input",
            value: value,
        };
    });

    renderAllNotes();
}

function checkIfOptionExists(value) {
    if (!value || !notesCategories) {
        return false;
    }

    for (var i = 0; i < notesCategories.length; i++) {
        var category = notesCategories[i];
        if (category && category.options && Array.isArray(category.options)) {
            for (var j = 0; j < category.options.length; j++) {
                var option = category.options[j];
                if (option && option.name) {
                    var optionValue = category.name + " > " + option.name;
                    if (optionValue === value) {
                        return true;
                    }
                }
            }
        }
    }
    return false;
}

function formatNumbersInText(text) {
    return text.replace(/\d{4,}/g, function (match) {
        var num = Number(match);
        return Number.isFinite(num) ? num.toLocaleString("ko-KR") : match;
    });
}

function formatNotesText(notes) {
    if (!notes || !notes.trim()) {
        return "";
    }
    return notes
        .split("\n")
        .map(function (line) {
            return line.trim();
        })
        .join("\n");
}

function resetNotesToEmpty() {
    notesList = [{ type: "select", value: "" }];
    renderAllNotes();
}

function initNotesUi() {
    loadNotesCategories();

    var btnAddNote = document.getElementById("btnAddNote");
    if (btnAddNote) {
        btnAddNote.addEventListener("click", function () {
            addNoteItem("select");
        });
    }

    notesList = [{ type: "select", value: "" }];
    renderAllNotes();
}

window.WdCalculatorNotesUI = {
    initNotesUi: initNotesUi,
    resetNotesToEmpty: resetNotesToEmpty,
    loadNotesCategories: loadNotesCategories,
    collectNotes: collectNotes,
    loadNotes: loadNotes,
    formatNotesText: formatNotesText,
    formatNumbersInText: formatNumbersInText,
    renderAllNotes: renderAllNotes,
};
