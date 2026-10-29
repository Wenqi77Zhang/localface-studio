"use strict";

// This page only explains the workflow. It never accepts files or calls an API.
const tablist = document.querySelector('[role="tablist"]');
const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));

function selectTab(selected, moveFocus = false) {
  for (const tab of tabs) {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !active;
  }
  if (moveFocus) selected.focus();
}

tablist.addEventListener("click", (event) => {
  const tab = event.target.closest('[role="tab"]');
  if (tab && tabs.includes(tab)) selectTab(tab);
});

tablist.addEventListener("keydown", (event) => {
  const current = tabs.indexOf(event.target);
  if (current < 0) return;
  let next;
  if (event.key === "ArrowDown") next = (current + 1) % tabs.length;
  if (event.key === "ArrowUp") next = (current - 1 + tabs.length) % tabs.length;
  if (event.key === "Home") next = 0;
  if (event.key === "End") next = tabs.length - 1;
  if (next === undefined) return;
  event.preventDefault();
  selectTab(tabs[next], true);
});
