import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function element(className = '') {
  return {
    className, children: [], listeners: {}, scrollTop: 0, scrollHeight: 1200,
    classList: {
      contains(name) { return className.split(' ').includes(name); },
      toggle() {}, add() {}, remove() {},
    },
    append(...nodes) {
      for (const node of nodes) {
        if (node.parentNode) node.parentNode.children = node.parentNode.children.filter(n => n !== node);
        node.parentNode = this;
        this.children.push(node);
      }
    },
    appendChild(node) { this.append(node); return node; },
    replaceChildren(...nodes) { this.children = []; this.scrollTop = 0; this.append(...nodes); },
    addEventListener(name, fn) { this.listeners[name] = fn; },
    setAttribute() {},
    querySelector(selector) {
      if (selector === '#scrollTabLatest' && this.innerHTML?.includes('scrollTabLatest')) {
        return this.latestButton ||= element();
      }
      return null;
    },
    querySelectorAll() { return []; },
    cloneNode() { return element(className); },
    scrollTo({top}) { this.scrollTop = top; },
    closest() { return this; },
    focus() { this.focused = true; },
    showModal() { this.open = true; },
    close() { this.open = false; this.listeners.close?.(); },
  };
}

function pixelSetup() {
  const feed = element();
  feed.append(element('msg-user'), element('msg-system'), element('msg-loading'));
  const wrap = element(), tab = element();
  tab.id = 'tabChat'; tab.dataset = {tab: 'chat'};
  const nodes = {chatFeed: feed, journalContent: wrap};
  let init;
  const context = vm.createContext({gameState: null, document: {
    getElementById: id => nodes[id] || null,
    createElement: () => element(),
    querySelectorAll: () => [tab],
    addEventListener: (_, fn) => { init = fn; },
  }});
  vm.runInContext(readFileSync(new URL('./pixel.js', import.meta.url), 'utf8'), context);
  init(); tab.onclick();
  return {feed, wrap, ui: vm.runInContext('PixelUI', context)};
}

test('right chat tab shows local messages even before journal API succeeds', () => {
  const {wrap} = pixelSetup();
  assert.equal(wrap.children.length, 2);
  assert.match(wrap.children[0].innerHTML, /2 ข้อความ/);
  assert.equal(wrap.children[1].children.length, 2);
  assert.equal(wrap.scrollTop, wrap.scrollHeight);
});

test('latest button and new answers scroll the actual journal viewport', () => {
  const {feed, wrap, ui} = pixelSetup();
  wrap.scrollTop = 0;
  wrap.children[0].latestButton.listeners.click();
  assert.equal(wrap.scrollTop, wrap.scrollHeight);
  wrap.scrollTop = 0;
  feed.append(element('msg-system'));
  ui.updateChatTab();
  assert.equal(wrap.children[1].children.length, 3);
  assert.equal(wrap.scrollTop, wrap.scrollHeight);
});

test('rebuilt header history button opens the original log and restores it on close', () => {
  const nodes = Object.fromEntries(['historyDialog', 'chatFeed', 'latestChatHost',
    'historyChatHost', 'closeHistory', 'historyLatest'].map(id => [id, element()]));
  nodes.chatFeed.append(element('msg-user'), element('msg-system'));
  nodes.latestChatHost.append(nodes.chatFeed);
  let init;
  const handlers = {};
  vm.runInNewContext(readFileSync(new URL('./history.js', import.meta.url), 'utf8'), {
    window: {addEventListener: (_, fn) => { init = fn; }},
    document: {
      getElementById: id => nodes[id],
      addEventListener: (event, fn) => { handlers[event] = fn; },
      querySelectorAll: () => [], body: element(),
    },
    MutationObserver: class { observe() {} },
  });
  init();
  const newHeaderButton = element();
  handlers.click({target: newHeaderButton});
  assert.equal(nodes.historyDialog.open, true);
  assert.equal(nodes.chatFeed.parentNode, nodes.historyChatHost);
  assert.equal(nodes.chatFeed.children.length, 2);
  nodes.historyDialog.close();
  assert.equal(nodes.chatFeed.parentNode, nodes.latestChatHost);
  assert.equal(newHeaderButton.focused, true);
});
