/* Copyright 2012 Mozilla Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const { OPS } = globalThis.pdfjsLib || (await import("pdfjs-lib"));

const opMap = Object.create(null);
for (const key in OPS) {
  opMap[OPS[key]] = key;
}

const FontInspector = (function FontInspectorClosure() {
  let fonts;
  let active = false;
  const fontAttribute = "data-font-name";
  function removeSelection() {
    const divs = document.querySelectorAll(`span[${fontAttribute}]`);
    for (const div of divs) {
      div.className = "";
    }
  }
  function resetSelection() {
    const divs = document.querySelectorAll(`span[${fontAttribute}]`);
    for (const div of divs) {
      div.className = "debuggerHideText";
    }
  }
  function selectFont(fontName, show) {
    const divs = document.querySelectorAll(
      `span[${fontAttribute}=${fontName}]`
    );
    for (const div of divs) {
      div.className = show ? "debuggerShowText" : "debuggerHideText";
    }
  }
  function textLayerClick(e) {
    if (
      !e.target.dataset.fontName ||
      e.target.tagName.toUpperCase() !== "SPAN"
    ) {
      return;
    }
    const fontName = e.target.dataset.fontName;
    const selects = document.getElementsByTagName("input");
    for (const select of selects) {
      if (select.dataset.fontName !== fontName) {
        continue;
      }
      select.checked = !select.checked;
      selectFont(fontName, select.checked);
      select.scrollIntoView();
    }
  }
  return {
    // Properties/functions needed by PDFBug.
    id: "FontInspector",
    name: "Font Inspector",
    panel: null,
    manager: null,
    init() {
      const panel = this.panel;
      const tmp = document.createElement("button");
      tmp.addEventListener("click", resetSelection);
      tmp.textContent = "Refresh";
      panel.append(tmp);

      fonts = document.createElement("div");
      panel.append(fonts);
    },
    cleanup() {
      fonts.textContent = "";
    },
    enabled: false,
    get active() {
      return active;
    },
    set active(value) {
      active = value;
      if (active) {
        document.body.addEventListener("click", textLayerClick, true);
        resetSelection();
      } else {
        document.body.removeEventListener("click", textLayerClick, true);
        removeSelection();
      }
    },
    // FontInspector specific functions.
    fontAdded(fontObj, url) {