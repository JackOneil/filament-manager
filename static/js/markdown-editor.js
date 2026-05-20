        function markdownEditor(config) {
            return {
                mode: config.defaultMode || 'visual',
                value: config.initialValue || '',
                placeholder: config.placeholder || '',
                editorHeight: config.defaultHeight || 260,
                lastVisualRange: null,
                init() {
                    if (this.$refs.source) {
                        this.value = this.$refs.source.value || this.value || '';
                    }
                    this.refreshVisual();
                    if (this.$refs.visual) {
                        this.$refs.visual.addEventListener('keydown', this.handleVisualKeydown.bind(this));
                        this.$refs.visual.addEventListener('mousedown', this.handleVisualMouseDown.bind(this));
                        this.$refs.visual.addEventListener('keyup', this.saveVisualSelection.bind(this));
                        this.$refs.visual.addEventListener('mouseup', this.saveVisualSelection.bind(this));
                        this.$refs.visual.addEventListener('focus', this.saveVisualSelection.bind(this));
                    }
                    if (this.mode === 'preview') {
                        this.syncPreview();
                    }
                },
                setMode(nextMode) {
                    if (this.mode === nextMode) return;
                    if (this.mode === 'visual') {
                        this.syncFromVisual();
                    }
                    this.mode = nextMode;
                    if (nextMode === 'visual') {
                        this.$nextTick(() => this.refreshVisual());
                    }
                    if (nextMode === 'preview') {
                        this.syncPreview();
                    }
                },
                syncPreview() {
                    if (this.mode === 'visual') {
                        this.syncFromVisual();
                    }
                },
                refreshVisual() {
                    if (!this.$refs.visual) return;
                    this.$refs.visual.innerHTML = this.markdownToHtml(this.value || '');
                    this.lastVisualRange = null;
                },
                syncFromVisual() {
                    if (!this.$refs.visual) return;
                    this.value = this.htmlToMarkdown(this.$refs.visual.innerHTML);
                    if (this.$refs.source) {
                        this.$refs.source.value = this.value;
                    }
                },
                startResize(event) {
                    var startY = event.clientY;
                    var startHeight = this.editorHeight;
                    var self = this;
                    function onMove(moveEvent) {
                        self.editorHeight = Math.max(180, startHeight + (moveEvent.clientY - startY));
                    }
                    function onUp() {
                        window.removeEventListener('mousemove', onMove);
                        window.removeEventListener('mouseup', onUp);
                    }
                    window.addEventListener('mousemove', onMove);
                    window.addEventListener('mouseup', onUp);
                },
                apply(action) {
                    if (this.mode === 'visual') {
                        this.applyVisual(action);
                        this.syncFromVisual();
                    } else {
                        this.applyMarkdown(action);
                    }
                    if (this.mode === 'preview') {
                        this.syncPreview();
                    }
                },
                applyVisual(action) {
                    if (!this.$refs.visual) return;
                    this.$refs.visual.focus();
                    this.restoreVisualSelection();
                    if (action === 'bold') document.execCommand('bold');
                    if (action === 'italic') document.execCommand('italic');
                    if (action === 'h2') document.execCommand('formatBlock', false, 'h2');
                    if (action === 'ul') document.execCommand('insertUnorderedList');
                    if (action === 'ol') document.execCommand('insertOrderedList');
                    if (action === 'quote') document.execCommand('formatBlock', false, 'blockquote');
                    if (action === 'checkbox') {
                        this.insertTaskCheckbox();
                    }
                    if (action === 'link') {
                        var url = window.prompt('URL', 'https://');
                        if (url) document.execCommand('createLink', false, url);
                    }
                    if (action === 'code') {
                        document.execCommand('insertHTML', false, '<code>' + this.escapeHtml(window.getSelection().toString() || 'code') + '</code>');
                    }
                    this.saveVisualSelection();
                },
                saveVisualSelection() {
                    if (!this.$refs.visual) return;
                    var sel = window.getSelection();
                    if (!sel || !sel.rangeCount) return;
                    var range = sel.getRangeAt(0);
                    if (!this.$refs.visual.contains(range.startContainer) || !this.$refs.visual.contains(range.endContainer)) return;
                    this.lastVisualRange = range.cloneRange();
                },
                restoreVisualSelection() {
                    if (!this.lastVisualRange) return;
                    var sel = window.getSelection();
                    if (!sel) return;
                    sel.removeAllRanges();
                    sel.addRange(this.lastVisualRange);
                },
                applyMarkdown(action) {
                    var textarea = this.$refs.markdown;
                    if (!textarea) return;
                    var start = textarea.selectionStart || 0;
                    var end = textarea.selectionEnd || 0;
                    var selected = this.value.slice(start, end);
                    var result = this.value;
                    var nextCursor = end;

                    function replaceRange(prefix, suffix, fallback) {
                        var insert = prefix + (selected || fallback) + suffix;
                        result = result.slice(0, start) + insert + result.slice(end);
                        nextCursor = start + insert.length;
                    }

                    if (action === 'bold') replaceRange('**', '**', 'text');
                    if (action === 'italic') replaceRange('*', '*', 'text');
                    if (action === 'h2') replaceRange('## ', '', 'Heading');
                    if (action === 'quote') replaceRange('> ', '', 'Quote');
                    if (action === 'code') replaceRange('`', '`', 'code');
                    if (action === 'ul') replaceRange('- ', '', 'List item');
                    if (action === 'ol') replaceRange('1. ', '', 'List item');
                    if (action === 'checkbox') replaceRange('- [ ] ', '', '');
                    if (action === 'link') {
                        var href = window.prompt('URL', 'https://');
                        if (href) {
                            var text = selected || 'link';
                            var insert = '[' + text + '](' + href + ')';
                            result = result.slice(0, start) + insert + result.slice(end);
                            nextCursor = start + insert.length;
                        }
                    }

                    this.value = result;
                    this.$nextTick(() => {
                        textarea.focus();
                        textarea.setSelectionRange(nextCursor, nextCursor);
                    });
                },
                createTaskItemNode(innerHtml, checked) {
                    var li = document.createElement('li');
                    li.className = 'task-list-item';

                    var checkbox = document.createElement('input');
                    checkbox.type = 'checkbox';
                    checkbox.className = 'task-checkbox';
                    if (checked) checkbox.checked = true;

                    var text = document.createElement('span');
                    text.className = 'task-text';
                    text.innerHTML = innerHtml || '';

                    li.appendChild(checkbox);
                    li.appendChild(document.createTextNode(' '));
                    li.appendChild(text);
                    return li;
                },
                selectionTaskItem() {
                    var sel = window.getSelection();
                    if (!sel || !sel.rangeCount) return null;
                    var anchor = sel.anchorNode;
                    if (!anchor) return null;
                    var fromElement = anchor.nodeType === Node.ELEMENT_NODE ? anchor : anchor.parentElement;
                    if (!fromElement || !fromElement.closest) return null;
                    return fromElement.closest('li.task-list-item');
                },
                placeCaretInTaskItem(li, atEnd) {
                    if (!li) return;
                    var textWrap = li.querySelector('.task-text');
                    if (!textWrap) return;
                    var target = textWrap.firstChild;
                    if (!target) {
                        target = document.createTextNode('');
                        textWrap.appendChild(target);
                    }
                    var offset = atEnd ? target.textContent.length : 0;
                    var range = document.createRange();
                    range.setStart(target, offset);
                    range.collapse(true);
                    var sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(range);
                    this.saveVisualSelection();
                },
                // Returns the direct child-of-visual-editor element that contains `node`,
                // used to find the right insertion point for block-level elements.
                _blockAncestor(node) {
                    if (!node || !this.$refs.visual) return null;
                    var current = node.nodeType === Node.TEXT_NODE ? node.parentNode : node;
                    while (current && current !== this.$refs.visual) {
                        if (current.parentNode === this.$refs.visual) return current;
                        current = current.parentNode;
                    }
                    return null;
                },
                isTaskItemEmpty(li) {
                    if (!li) return true;
                    // Consider any non-checkbox content in the row, not only .task-text,
                    // because browser editing may temporarily place text outside helper spans.
                    var raw = '';
                    Array.from(li.childNodes || []).forEach(function (node) {
                        if (node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() === 'input') {
                            return;
                        }
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            raw += node.textContent || '';
                            return;
                        }
                        if (node.nodeType === Node.TEXT_NODE) {
                            raw += node.textContent || '';
                        }
                    });
                    return raw.replace(/\u00a0/g, ' ').trim() === '';
                },
                insertTaskCheckbox() {
                    this.restoreVisualSelection();
                    var sel = window.getSelection();
                    if (!sel || !sel.rangeCount) return;
                    var range = sel.getRangeAt(0);
                    var currentLi = this.selectionTaskItem();
                    var selectedHtml = this.rangeToInlineHtml(range);
                    range.deleteContents();
                    var insertedLi = null;

                    if (currentLi && currentLi.parentElement && currentLi.parentElement.matches('ul.task-list')) {
                        // Already inside a task list — insert new item after the current one.
                        insertedLi = this.createTaskItemNode(selectedHtml, false);
                        currentLi.parentElement.insertBefore(insertedLi, currentLi.nextSibling);
                    } else {
                        // Outside a task list — create a new list and insert it after the
                        // containing block element so we never nest a <ul> inside a <p>.
                        var ul = document.createElement('ul');
                        ul.className = 'task-list';
                        insertedLi = this.createTaskItemNode(selectedHtml, false);
                        ul.appendChild(insertedLi);
                        var block = this._blockAncestor(range.startContainer);
                        if (block) {
                            block.parentNode.insertBefore(ul, block.nextSibling);
                        } else {
                            // Fallback for completely empty editor.
                            this.$refs.visual.appendChild(ul);
                        }
                    }

                    this.placeCaretInTaskItem(insertedLi, false);
                    this.saveVisualSelection();
                },
                rangeToInlineHtml(range) {
                    if (!range || range.collapsed) return '';
                    var fragment = range.cloneContents();
                    var container = document.createElement('div');
                    container.appendChild(fragment);
                    return container.innerHTML;
                },
                handleVisualKeydown(event) {
                    if (!event || event.key !== 'Enter' || event.shiftKey) return;
                    var currentLi = this.selectionTaskItem();
                    if (!currentLi || !currentLi.parentElement || !currentLi.parentElement.matches('ul.task-list')) return;

                    event.preventDefault();

                    var taskList = currentLi.parentElement;
                    var nextTaskItem = currentLi.nextElementSibling;
                    if (this.isTaskItemEmpty(currentLi)) {
                        taskList.removeChild(currentLi);
                        if (nextTaskItem && nextTaskItem.matches('li.task-list-item')) {
                            this.placeCaretInTaskItem(nextTaskItem, false);
                        } else {
                            // Create an exit paragraph with a <br> placeholder — browsers
                            // (especially Chrome) need a <br> to render a visible cursor in
                            // an empty block; a bare empty-text-node is not a stable anchor
                            // and causes the cursor to silently drift back into the task list.
                            var paragraph = document.createElement('p');
                            paragraph.appendChild(document.createElement('br'));
                            if (taskList.parentElement) {
                                taskList.parentElement.insertBefore(paragraph, taskList.nextSibling);
                            }
                            if (!taskList.querySelector('li.task-list-item')) {
                                taskList.remove();
                            }
                            // setStart(element, 0) positions the cursor before the first
                            // child (<br>), which Chrome accepts as a real caret position.
                            var exitRange = document.createRange();
                            exitRange.setStart(paragraph, 0);
                            exitRange.collapse(true);
                            var exitSel = window.getSelection();
                            exitSel.removeAllRanges();
                            exitSel.addRange(exitRange);
                            this.saveVisualSelection();
                        }
                        this.syncFromVisual();
                        return;
                    }

                    var nextLi = this.createTaskItemNode('', false);
                    taskList.insertBefore(nextLi, currentLi.nextSibling);
                    this.placeCaretInTaskItem(nextLi, false);
                    // Keep DOM interaction stable for subsequent typing; source value will
                    // sync on further input/mode switch/submit as before.
                },
                handleVisualMouseDown(event) {
                    var target = event && event.target;
                    if (!target || !target.matches || !target.matches('input.task-checkbox')) return;
                    event.preventDefault();
                    var li = target.closest('li.task-list-item');
                    this.placeCaretInTaskItem(li, false);
                },
                escapeHtml(value) {
                    return String(value || '')
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#39;');
                },
                renderInline(value) {
                    var html = this.escapeHtml(value || '');
                    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
                    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+|mailto:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
                    html = html.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
                    html = html.replace(/(^|[^\*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
                    return html;
                },
                markdownToHtml(markdown) {
                    var lines = String(markdown || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
                    var blocks = [];
                    var paragraph = [];
                    var listType = null;
                    var listItems = [];
                    var quoteLines = [];
                    var inCode = false;
                    var codeLines = [];
                    var checkboxIndex = 0;
                    var self = this;

                    function flushParagraph() {
                        if (!paragraph.length) return;
                        blocks.push('<p>' + paragraph.map(line => self.renderInline(line)).join('<br>') + '</p>');
                        paragraph = [];
                    }
                    function flushList() {
                        if (!listItems.length) return;
                        if (listType === 'task') {
                            blocks.push('<ul class="task-list">' + listItems.join('') + '</ul>');
                        } else {
                            blocks.push('<' + listType + '>' + listItems.map(item => '<li>' + item + '</li>').join('') + '</' + listType + '>');
                        }
                        listItems = [];
                        listType = null;
                    }
                    function flushQuote() {
                        if (!quoteLines.length) return;
                        blocks.push('<blockquote>' + quoteLines.map(line => self.renderInline(line)).join('<br>') + '</blockquote>');
                        quoteLines = [];
                    }
                    function flushCode() {
                        if (!codeLines.length) return;
                        blocks.push('<pre><code>' + self.escapeHtml(codeLines.join('\n')) + '</code></pre>');
                        codeLines = [];
                    }

                    lines.forEach(function (line) {
                        var trimmed = line.trim();
                        if (inCode) {
                            if (trimmed.startsWith('```')) {
                                flushCode();
                                inCode = false;
                            } else {
                                codeLines.push(line);
                            }
                            return;
                        }
                        if (trimmed.startsWith('```')) {
                            flushParagraph();
                            flushList();
                            flushQuote();
                            inCode = true;
                            return;
                        }
                        if (!trimmed) {
                            flushParagraph();
                            flushList();
                            flushQuote();
                            return;
                        }
                        if (/^(#{1,6})\s+/.test(line)) {
                            flushParagraph();
                            flushList();
                            flushQuote();
                            var level = line.match(/^(#{1,6})\s+/)[1].length;
                            blocks.push('<h' + level + '>' + self.renderInline(line.replace(/^(#{1,6})\s+/, '')) + '</h' + level + '>');
                            return;
                        }
                        if (/^>\s?/.test(line)) {
                            flushParagraph();
                            flushList();
                            quoteLines.push(line.replace(/^>\s?/, ''));
                            return;
                        }
                        var taskMatch = line.match(/^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/);
                        if (taskMatch) {
                            flushParagraph();
                            flushQuote();
                            if (listType && listType !== 'task') flushList();
                            listType = 'task';
                            var cbChecked = taskMatch[1].toLowerCase() === 'x';
                            var cbIdx = checkboxIndex++;
                            listItems.push('<li class="task-list-item"><input type="checkbox" class="task-checkbox" data-index="' + cbIdx + '"' + (cbChecked ? ' checked' : '') + '> <span class="task-text">' + self.renderInline(taskMatch[2]) + '</span></li>');
                            return;
                        }
                        if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
                            flushParagraph();
                            flushQuote();
                            var nextType = /^\s*\d+\.\s+/.test(line) ? 'ol' : 'ul';
                            if (listType && listType !== nextType) flushList();
                            listType = nextType;
                            listItems.push(self.renderInline(line.replace(/^\s*(?:[-*+]|\d+\.)\s+/, '')));
                            return;
                        }
                        flushList();
                        flushQuote();
                        paragraph.push(line);
                    });

                    flushParagraph();
                    flushList();
                    flushQuote();
                    if (inCode) flushCode();
                    return blocks.join('');
                },
                htmlToMarkdown(html) {
                    var wrapper = document.createElement('div');
                    wrapper.innerHTML = html || '';
                    return this.nodeToMarkdown(wrapper).trim();
                },
                nodeToMarkdown(node) {
                    var self = this;
                    return Array.from(node.childNodes).map(function (child) {
                        if (child.nodeType === Node.TEXT_NODE) {
                            return child.textContent.replace(/\u00a0/g, ' ');
                        }
                        if (child.nodeType !== Node.ELEMENT_NODE) {
                            return '';
                        }
                        var tag = child.tagName.toLowerCase();
                        if (tag === 'strong' || tag === 'b') return '**' + self.nodeToMarkdown(child).trim() + '**';
                        if (tag === 'em' || tag === 'i') return '*' + self.nodeToMarkdown(child).trim() + '*';
                        if (tag === 'code' && child.parentElement && child.parentElement.tagName.toLowerCase() !== 'pre') return '`' + child.textContent + '`';
                        if (tag === 'a') return '[' + self.nodeToMarkdown(child).trim() + '](' + (child.getAttribute('href') || '') + ')';
                        if (tag === 'h1') return '# ' + self.nodeToMarkdown(child).trim() + '\n\n';
                        if (tag === 'h2') return '## ' + self.nodeToMarkdown(child).trim() + '\n\n';
                        if (tag === 'h3') return '### ' + self.nodeToMarkdown(child).trim() + '\n\n';
                        if (tag === 'blockquote') return self.nodeToMarkdown(child).split('\n').filter(Boolean).map(line => '> ' + line).join('\n') + '\n\n';
                        if (tag === 'pre') return '```\n' + child.textContent.trim() + '\n```\n\n';
                        if (tag === 'input' && child.getAttribute('type') === 'checkbox') return '';
                        if (tag === 'ul' && child.classList.contains('task-list')) {
                            return Array.from(child.children).map(function (li) {
                                var cb = li.querySelector('input[type="checkbox"]');
                                var checked = cb && cb.checked;
                                var text = Array.from(li.childNodes).filter(function (n) {
                                    return !(n.nodeType === Node.ELEMENT_NODE && n.tagName.toLowerCase() === 'input');
                                }).map(function (n) {
                                    return n.nodeType === Node.TEXT_NODE ? n.textContent.replace(/\u00a0/g, ' ') : self.nodeToMarkdown(n);
                                }).join('').trim();
                                return '- [' + (checked ? 'x' : ' ') + '] ' + text;
                            }).join('\n') + '\n\n';
                        }
                        if (tag === 'ul') {
                            return Array.from(child.children).map(li => '- ' + self.nodeToMarkdown(li).trim()).join('\n') + '\n\n';
                        }
                        if (tag === 'ol') {
                            return Array.from(child.children).map(function (li, index) {
                                return (index + 1) + '. ' + self.nodeToMarkdown(li).trim();
                            }).join('\n') + '\n\n';
                        }
                        if (tag === 'br') return '\n';
                        if (tag === 'div' || tag === 'p') return self.nodeToMarkdown(child).trim() + '\n\n';
                        if (tag === 'li') return self.nodeToMarkdown(child);
                        return self.nodeToMarkdown(child);
                    }).join('');
                },
            };
        }
