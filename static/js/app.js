// V54: Returning to the original standalone AI chat. No history sidebar or fetch interception.

// Logic giao diện: chat AI, đăng nhập/điều hướng, nhân viên & chấm công, dashboard


// ===== Trợ lý AI =====
    function deepQuery(root, selector) {
        if (!root) return null;
 
        const direct = root.querySelector?.(selector);
        if (direct) return direct;
 
        const nodes = root.querySelectorAll?.('*') || [];
        for (const node of nodes) {
            if (node.shadowRoot) {
                const found = deepQuery(node.shadowRoot, selector);
                if (found) return found;
            }
        }
        return null;
    }
 
    function deepQueryAll(root, selector) {
        const result = [];
        if (!root) return result;
 
        const direct = root.querySelectorAll?.(selector) || [];
        result.push(...direct);
 
        const nodes = root.querySelectorAll?.('*') || [];
        for (const node of nodes) {
            if (node.shadowRoot) {
                result.push(...deepQueryAll(node.shadowRoot, selector));
            }
        }
        return result;
    }
 
    function setInputValue(input, value) {
        if (!input) return false;
 
        input.focus();
 
        if (input.isContentEditable) {
            input.textContent = value;
            input.dispatchEvent(new InputEvent('input', {
                bubbles: true,
                composed: true,
                inputType: 'insertText',
                data: value
            }));
            input.dispatchEvent(new Event('change', {
                bubbles: true,
                composed: true
            }));
            return true;
        }
 
        const proto = input instanceof HTMLTextAreaElement
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
 
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (setter) setter.call(input, value);
        else input.value = value;
 
        input.dispatchEvent(new Event('input', {
            bubbles: true,
            composed: true
        }));
        input.dispatchEvent(new Event('change', {
            bubbles: true,
            composed: true
        }));
 
        return true;
    }
 
    function trySendToVanna(text) {
        const host = document.getElementById('vannaChat');
        if (!host) return false;
 
        // Nếu component expose API public thì ưu tiên API đó.
        for (const methodName of ['sendMessage', 'send', 'ask']) {
            if (typeof host[methodName] === 'function') {
                try {
                    const result = host[methodName](text);
                    if (result !== false) return true;
                } catch (_) {}
            }
        }
 
        const root = host.shadowRoot || host;
 
        // Tìm ô nhập bên trong light DOM / shadow DOM.
        const input = deepQuery(
            root,
            'textarea, input[type="text"], input:not([type]), [contenteditable="true"]'
        );
 
        if (!input) return false;
        if (!setInputValue(input, text)) return false;
 
        const buttons = deepQueryAll(root, 'button');
        const sendButton = buttons.find(button => {
            const label = [
                button.getAttribute('aria-label'),
                button.getAttribute('title'),
                button.getAttribute('data-testid'),
                button.getAttribute('data-test'),
                button.textContent
            ]
                .filter(Boolean)
                .join(' ')
                .toLowerCase();
 
            return (
                label.includes('send') ||
                label.includes('gửi') ||
                label.includes('submit')
            );
        });
 
        if (sendButton && !sendButton.disabled) {
            sendButton.click();
            return true;
        }
 
        // Tìm form gần ô nhập.
        const form = input.closest?.('form') || deepQuery(root, 'form');
        if (form) {
            try {
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.dispatchEvent(new Event('submit', {
                        bubbles: true,
                        cancelable: true,
                        composed: true
                    }));
                }
                return true;
            } catch (_) {}
        }
 
        // Cuối cùng mô phỏng Enter.
        const keyOptions = {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true,
            composed: true
        };
 
        input.dispatchEvent(new KeyboardEvent('keydown', keyOptions));
        input.dispatchEvent(new KeyboardEvent('keypress', keyOptions));
        input.dispatchEvent(new KeyboardEvent('keyup', keyOptions));
 
        return true;
    }
 
    function showCopyNotice(text) {
        let notice = document.getElementById('copyNotice');
 
        if (!notice) {
            notice = document.createElement('div');
            notice.id = 'copyNotice';
            notice.style.cssText =
                'position:fixed;right:24px;bottom:24px;z-index:9999;' +
                'background:#0f766e;color:#fff;padding:10px 14px;' +
                'border-radius:10px;font-size:12px;font-weight:700;' +
                'box-shadow:0 8px 24px rgba(0,0,0,.16)';
            document.body.appendChild(notice);
        }
 
        notice.textContent = '✓ Đã copy câu hỏi — Vui lòng dán vào ô chat và nhấn Enter';
        notice.style.display = 'block';
 
        clearTimeout(window.__copyNoticeTimer);
        window.__copyNoticeTimer = setTimeout(
            () => notice.style.display = 'none',
            3000
        );
    }
 
    function copyQuestionFallback(text) {
        const fallback = () => {
            const area = document.createElement('textarea');
            area.value = text;
            area.style.position = 'fixed';
            area.style.left = '-9999px';
            area.style.top = '0';
            document.body.appendChild(area);
            area.focus();
            area.select();
 
            try {
                document.execCommand('copy');
                showCopyNotice(text);
            } catch (_) {
                prompt('Hãy copy câu hỏi này:', text);
            }
 
            area.remove();
        };
 
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text)
                .then(() => showCopyNotice(text))
                .catch(fallback);
        } else {
            fallback();
        }
    }
 
    async function askQuestion(text) {
        if (!text) return false;
 
        showView('chat');
 
        // Web component có thể render shadow DOM sau khi tab Chat được mở.
        // Thử vài lần trong thời gian ngắn trước khi fallback sang copy.
        const delays = [0, 100, 300, 700];
 
        for (const delay of delays) {
            if (delay) {
                await new Promise(resolve => setTimeout(resolve, delay));
            }
 
            try {
                if (trySendToVanna(text)) {
                    return true;
                }
            } catch (e) {
                console.warn('Không thể tự gửi câu hỏi vào Vanna:', e);
            }
        }
 
        // Không phá chức năng cũ nếu component Vanna không cho truy cập input.
        copyQuestionFallback(text);
        return false;
    }
 
    function newChat() {
 
        window.location.reload();
 
    }


// ===== Lõi: đăng nhập, điều hướng, bộ lọc =====
    let dashboardPOs = [];
    let selectedPOCode = null;
    try { selectedPOCode = localStorage.getItem('selectedPOCode') || null; } catch (e) {}
 
    function saveSelectedPO(code) {
        selectedPOCode = code || null;
        try {
            if (code) localStorage.setItem('selectedPOCode', code);
            else localStorage.removeItem('selectedPOCode');
        } catch (e) {
            console.warn('Không thể lưu PO đã chọn:', e);
        }
    }
 
    function toggleSideNav(forceOpen = null) {
        const nav = document.getElementById('sideNav');
        const toggle = document.getElementById('navToggle');
        if (!nav || !toggle) return;
        const shouldOpen = forceOpen === null ? nav.classList.contains('closed') : !!forceOpen;
        nav.classList.toggle('closed', !shouldOpen);
        toggle.setAttribute('aria-expanded', String(shouldOpen));
        toggle.title = shouldOpen ? 'Ẩn thanh điều hướng' : 'Mở thanh điều hướng';
    }
 
    window.currentUser = null;
    (function () {
        const rawFetch = window.fetch.bind(window);
        window.fetch = async function (...args) {
            const res = await rawFetch(...args);
            const url = String(args[0] && args[0].url ? args[0].url : args[0]);
            if (res.status === 401 && url.indexOf('/api/') !== -1 && url.indexOf('/api/auth/login') === -1) {
                window.location.href = '/login';
            }
            return res;
        };
    })();
    async function initAuth() {
        try {
            const res = await fetch('/api/auth/me');
            if (!res.ok) return;
            const me = await res.json();
            window.currentUser = me;

            document.body.classList.toggle('mes-technician', me.role === 'technician');
            document.body.classList.toggle('mes-team-lead', me.role === 'team_lead');
            document.body.classList.toggle('mes-customer', me.role === 'customer');
            document.getElementById('userName').textContent = me.full_name || me.username || '';
            document.getElementById('userAvatar').textContent = String(me.full_name || me.username || '?').trim().split(/\s+/).pop().charAt(0).toUpperCase();
            const roleEl = document.getElementById('userRole');
            roleEl.textContent = me.role_label || '';
            roleEl.removeAttribute('title');
            document.getElementById('userBox').style.display = 'block';
            // Tất cả vai trò dùng chung Tổng quan công đơn lấy từ customer_orders.
            document.getElementById('internalDashboard').style.display='none';
            document.getElementById('customerDashboard').style.display='';
            const orderTable = document.getElementById('ordersView').querySelector('.panel:nth-child(2)');
            if (orderTable && orderTable.parentElement !== document.getElementById('customerDashboardOrders')) {
                document.getElementById('customerDashboardOrders').appendChild(orderTable);
            }
            const totalTitle = document.querySelector('#coTotal')?.previousElementSibling;
            if (totalTitle) totalTitle.textContent = me.role === 'admin' ? 'Tổng số lượng' : me.role === 'customer' ? 'Tổng công đơn' : 'Công đơn của xưởng';
            const quantityTitle=document.querySelector('#coQuantity')?.previousElementSibling;
            if(quantityTitle) quantityTitle.textContent=me.role==='customer'?'Tổng số lượng':me.role==='admin'?'Đang kế hoạch':'Chờ Admin duyệt';
            const productionTitle=document.querySelector('#coProduction')?.previousElementSibling;
            if(productionTitle) productionTitle.textContent='Đang sản xuất';
            const waitingTitle=document.querySelector('#coWaiting')?.previousElementSibling;
            if(waitingTitle) waitingTitle.textContent=me.role==='admin'?'Đã hoàn thành':'Chờ tiếp nhận';
            const adminLabel = document.getElementById('navAdminLabel');
            if(adminLabel) adminLabel.style.display = me.role === 'admin' ? '' : 'none';
            // Technician and team lead: hide employee/customer management menus; AI remains available.
            if (me.role === 'technician' || me.role === 'team_lead') {
                ['tabEmployees', 'tabCustomers'].forEach(id => {
                    const item = document.getElementById(id);
                    if (item) { item.hidden = true; item.style.setProperty('display', 'none', 'important'); }
                });
            }
            if(me.role === 'customer') {
                ['tabWork','tabEmployees','tabCustomers','navAdminLabel','tabOrders'].forEach(id=>{const el=document.getElementById(id);if(el){el.hidden=true;el.style.setProperty('display','none','important');}});
                document.getElementById('tabChat').onclick=()=>showView('customerChat');
                showView('dashboard');
            } else if (me.role === 'team_lead') {
                const tab = document.getElementById('tabCustomers');
                if(tab) { tab.style.display = 'none'; } // Tổ trưởng duyệt trực tiếp ở Tổng quan công đơn
            }
            poUpdateAdminUI();
            const workTab = document.getElementById('tabWork');
            if (workTab) workTab.textContent = '📋 Công việc giao ngay';
            if (typeof restoreWorkAssignmentDot === 'function') restoreWorkAssignmentDot(me);
            if (typeof startWorkDeadlinePolling === 'function') startWorkDeadlinePolling();
            if (typeof coStartNoticePolling === 'function') coStartNoticePolling(me);
            if (currentView === 'work') updateTopbar('work');
            if (me.role !== 'admin') {
                ['tabEmployees', 'tabCustomers', 'navAdminLabel'].forEach(id => {
                    const el = document.getElementById(id); if (el) el.style.display = 'none';
                });
            }
            loadCustomerOrders();
            restoreDoubleClickedMenu();
        } catch (e) { console.error('Auth/menu restore:', e); }
    }
    async function logout() {
        if (typeof stopWorkDeadlinePolling === 'function') stopWorkDeadlinePolling();
        if (typeof coStopNoticePolling === 'function') coStopNoticePolling();
        window.currentUser = null;
        try { await fetch('/api/auth/logout', {method: 'POST'}); } catch (e) {}
        window.location.href = '/login';
    }
    initAuth();
    if (window.innerWidth <= 800) toggleSideNav(false);
 
    const VIEW_TITLES = {
        dashboard: ['Tổng quan công đơn', 'Theo dõi công đơn và trạng thái xử lý'],
        orders: ['Tạo công đơn', 'Gửi yêu cầu sản xuất đến tổ trưởng'],
        customerChat: ['AI Assistant', 'Tra cứu trạng thái công đơn'],
        chat: ['Trợ lý AI', 'Phân tích dữ liệu sản xuất bằng ngôn ngữ tự nhiên'],
        employees: ['Nhân viên', 'Danh sách và trạng thái nhân sự'],
        customers: ['Khách hàng', window.currentUser?.role === 'team_lead' ? 'Duyệt công đơn khách hàng thuộc xưởng phụ trách' : 'Danh sách công ty và tài khoản khách hàng'],
        
        work: ['Công việc giao ngay', 'Giao việc, báo cáo, duyệt và lịch sử công việc']

    };
    let currentView = 'dashboard';
    // Double-click vào bất cứ mục menu: reload toàn bộ trang, giữ lại tab hiện tại.
    // Dùng sessionStorage để không làm thay đổi tab mặc định trong lần đăng nhập mới.
    const MENU_RELOAD_KEY = 'mes_menu_doubleclick_restore_v9';
    function refreshMenuView(view) {
        const allowed = ['dashboard','orders','chat','customerChat','work','employees','customers'];
        if (!allowed.includes(view)) return;
        try { sessionStorage.setItem(MENU_RELOAD_KEY, view); } catch (e) {}
        window.location.reload();
    }
    function restoreDoubleClickedMenu() {
        let view = null;
        try { view = sessionStorage.getItem(MENU_RELOAD_KEY); sessionStorage.removeItem(MENU_RELOAD_KEY); } catch (e) {}
        if (!view) return;
        // Quyền truy cập luôn được showView kiểm tra trước khi hiển thị.
        showView(view);
    }
    function refreshCurrentView() {
        if (currentView === 'orders') loadCustomerOrders();
        else if (currentView === 'customerChat') { /* AI chat: keep conversation without clearing the user message. */ }
        else if (currentView === 'dashboard') {
            if (window.currentUser?.role === 'customer') loadCustomerOrders();
            else { loadDashboard(); loadCustomerOrders(); }
        }
        else if (currentView === 'employees') loadEmployees();
        else if (currentView === 'customers') (window.currentUser?.role === 'team_lead' ? loadCustomerOrders() : loadCustomers());
        
        else if (currentView === 'work') loadWork();

    }
    function updateTopbar(view) {
        currentView = view;
        document.body.classList.toggle('work-no-topbar', view === 'work');
        // Trang AI khach hang su dung toan bo khong gian, khong hien header chung.
        document.body.classList.toggle('customer-ai-no-topbar', view === 'customerChat');
        document.body.classList.toggle('internal-ai-fullscreen', view === 'chat' || view === 'customerChat');
        const t = VIEW_TITLES[view]; if (!t) return;
        const title = document.querySelector('.page-title'), sub = document.querySelector('.page-subtitle');
        if (title) title.textContent = view === 'work' && window.currentUser?.role === 'technician' ? 'Công việc giao ngay' : t[0];
        if (sub) sub.textContent = view === 'work' && window.currentUser?.role === 'technician' ? 'Danh sách công việc được giao và lịch sử xử lý' : t[1];
    }
    (function tickDate() {
        const el = document.getElementById('topDate');
        if (el) el.textContent = new Date().toLocaleDateString('vi-VN', {weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric'});
    })();
 
    function ensureInternalAI() {
        if (!window.currentUser || !['admin', 'team_lead', 'technician', 'customer'].includes(window.currentUser.role)) return;
        const customerMode = window.currentUser.role === 'customer';
        const mount = document.getElementById(customerMode ? 'customerVannaMount' : 'vannaMount');
        if (!mount || mount.querySelector('vanna-chat')) return;
        const origin = window.location.origin;
        const chat = document.createElement('vanna-chat');
        chat.id = 'vannaChat';
        chat.setAttribute('api-base', origin);
        chat.setAttribute('sse-endpoint', origin + (customerMode ? '/api/customer-orders/assistant/vanna-sse' : '/api/vanna/v2/chat_sse'));
        // Keep existing AI response transport and role-specific permissions.
        mount.appendChild(chat);
        // Render the heading in the visible page, outside Vanna's Shadow DOM.
        const welcomeHost = mount.closest('.vanna-container');
        if(welcomeHost){
            welcomeHost.querySelector('.mes-center-welcome')?.remove();
            const greeting=document.createElement('div');
            greeting.className='mes-center-welcome';
            greeting.textContent='Tôi có thể giúp gì bạn?';
            welcomeHost.appendChild(greeting);
            const hideGreeting=()=>greeting.classList.add('mes-welcome-dismissed');
            chat.addEventListener('keydown',e=>{
                if(e.key==='Enter' && !e.shiftKey)hideGreeting();
            },true);
            chat.addEventListener('click',e=>{
                const path=e.composedPath?.()||[];
                if(path.some(el=>el?.tagName==='BUTTON' && /send|gửi/i.test((el.getAttribute('aria-label')||'')+' '+(el.getAttribute('title')||''))))hideGreeting();
            },true);
        }
        // V56: Remove fixed role-based suggested questions altogether.
        // Vanna's native text input and message submission are unchanged.
        const card = mount.closest('.chat-card');
        card?.querySelectorAll('.mes-role-suggestions').forEach(el => el.remove());
        // Vietnamese UI for all roles, including nested open shadow DOM in Vanna.
        // Does not change AI transport, permissions, or SQL access.
        {
            const phrases = [
                ['Welcome to Vanna AI', 'Chào mừng đến với Trợ lý AI Nhà máy'],
                ["I'm your AI data analyst assistant. Ask me anything about your data in plain English!", ''],
                ['Tôi là trợ lý AI phân tích dữ liệu. Hãy hỏi về công đơn, tiến độ và sản xuất bằng tiếng Việt!', ''],
                ["Type `/help` to see what I can do.", ''],
                ['Nhập /help để xem các chức năng tôi có thể hỗ trợ.', ''],
                ['Start a conversation', 'Xin chào! Tôi có thể hỗ trợ gì cho bạn?'],
                ['Type your message below to begin chatting', 'Hãy nhập câu hỏi để bắt đầu trò chuyện.'],
                ['Ask me anything...', 'Nhập câu hỏi của bạn...'],
                ['Ask a question...', 'Nhập câu hỏi của bạn...'],
                ['No tasks yet', 'Chưa có tác vụ'],
                ['Choose an option or type a message', ''],
                ['Chọn chức năng hoặc nhập câu hỏi', ''],
                ['Connection failed', 'Kết nối thất bại'],
                ['Unable to reach server', 'Không thể kết nối đến máy chủ'],
                ['Response complete', 'Đã hoàn tất phản hồi'],
                ['Sẵn sàng for next message', ''],
                ['Ready for next message', ''],
                ['Ready', ''],
            ];
            const visited = new WeakSet();
            let queued = false;
            const translateText = value => {
                let result = value;
                for (const [from, to] of phrases) {
                    if (result.includes(from)) result = result.split(from).join(to);
                }
                return result;
            };
            const applyTranslation = root => {
                // Inspect all nested shadow roots: web components can nest several levels.
                const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
                let node;
                while ((node = walker.nextNode())) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const original = node.nodeValue || '';
                        const translated = translateText(original);
                        if (translated !== original) {
                            // Remove only the informational paragraph, never chat actions or container.
                            const parent = node.parentElement;
                            const removable = parent && ['P','SPAN'].includes(parent.tagName)
                                && parent.textContent.trim() === original.trim()
                                && translated.trim() === '';
                            if (removable) parent.remove();
                            else node.nodeValue = translated;
                        }
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        for (const name of ['placeholder', 'aria-label', 'title']) {
                            const original = node.getAttribute(name);
                            if (original) {
                                const translated = translateText(original);
                                if (original !== translated) node.setAttribute(name, translated);
                            }
                        }
                        if (node.shadowRoot) {
                            observeRoot(node.shadowRoot);
                            applyTranslation(node.shadowRoot);
                        }
                    }
                }
            };
            const localize = () => {
                queued = false;
                if (!chat.isConnected) return;
                applyTranslation(chat);
                if (chat.shadowRoot) {observeRoot(chat.shadowRoot);applyTranslation(chat.shadowRoot);}
                // Remove the introductory Vanna banner for all roles without touching messages,
                // composer, API requests, or permissions. Supports nested open shadow roots.
                const removeWelcome = root => {
                    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                    const matches = [];
                    let textNode;
                    while ((textNode = walker.nextNode())) {
                        if ((textNode.nodeValue || '').includes('Chào mừng đến với Trợ lý AI Nhà máy')) {
                            matches.push(textNode);
                        }
                    }
                    for (const textNode of matches) {
                        const title = 'Chào mừng đến với Trợ lý AI Nhà máy';
                        const heading = textNode.parentElement;
                        if (!heading) continue;
                        let target = heading;
                        // Remove the outer banner wrapper only when it contains this heading
                        // (possibly with the waving-hand emoji), never the chat layout itself.
                        for (let depth = 0; depth < 5; depth++) {
                            const parent = target.parentElement;
                            if (!parent || parent === chat || parent === root.host) break;
                            const content = (parent.textContent || '').trim().replace(/\s+/g,' ');
                            if (!content.includes(title) || content.length > title.length + 12) break;
                            if (parent.querySelector('button,input,textarea,vanna-chat')) break;
                            target = parent;
                        }
                        // Keep references to ancestors before removing the heading/banner.
                        // Previously removing only the heading left an empty bordered strip.
                        const ancestors = [];
                        let ancestor = target.parentElement;
                        for (let i=0; ancestor && i<4 && ancestor!==chat && ancestor!==root.host; i++,ancestor=ancestor.parentElement) {
                            ancestors.push(ancestor);
                        }
                        target.remove();
                        // Remove empty decorative wrappers, but never chat messages/input/layout.
                        for (const box of ancestors) {
                            if (!box.isConnected) continue;
                            if ((box.textContent||'').trim()) break;
                            if (box.querySelector('button,input,textarea,[contenteditable],vanna-chat')) break;
                            const rect=box.getBoundingClientRect();
                            if (rect.height > 200 || rect.width < 200) break;
                            box.remove();
                        }
                    }
                    root.querySelectorAll?.('*').forEach(el => {
                        if (el.shadowRoot) removeWelcome(el.shadowRoot);
                    });
                };
                removeWelcome(chat);
                if (chat.shadowRoot) removeWelcome(chat.shadowRoot);
                // Customer Vanna builds an extra large dashed welcome card.
                // Remove ONLY that decorative empty-state card; keep the app's
                // single centered welcome title and the entire chat composer.
                {
                    const hideCustomerNativeWelcome = root => {
                        const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        let node;
                        while ((node = tw.nextNode())) {
                            const phrase=(node.nodeValue||'').trim();
                            if (!/^(Tôi có thể giúp gì bạn\?|How can I help you\?|Xin chào.*)$/i.test(phrase)) continue;
                            let el=node.parentElement, candidate=null;
                            for (let i=0; el && i<7; i++,el=el.parentElement) {
                                if (el===chat || el===root.host) break;
                                if (el.querySelector('textarea,input,button,[contenteditable],vanna-chat')) break;
                                const rect=el.getBoundingClientRect();
                                const style=getComputedStyle(el);
                                if (rect.width>300 && rect.height>100 && rect.height<550 &&
                                    (style.borderStyle.includes('dashed') || style.borderTopStyle==='dashed' || style.borderLeftStyle==='dashed')) {
                                    candidate=el;break;
                                }
                            }
                            // For non-dashed versions, hide just the heading, not chat contents.
                            if (!candidate) candidate=node.parentElement;
                            if(candidate) candidate.style.setProperty('display','none','important');
                        }
                        root.querySelectorAll?.('*').forEach(el=>{if(el.shadowRoot) hideCustomerNativeWelcome(el.shadowRoot);});
                    };
                    hideCustomerNativeWelcome(chat);
                    if(chat.shadowRoot) hideCustomerNativeWelcome(chat.shadowRoot);
                }
                // An older build removed the welcome text but left its empty 1px
                // outlined card. Remove only tiny, blank, non-interactive panels
                // near the top of Vanna's message area (not the composer/status bar).
                const cleanEmptyWelcomeOutlines = root => {
                    const viewport = chat.getBoundingClientRect();
                    if (viewport.width < 300) return;
                    for (const el of [...root.querySelectorAll('*')]) {
                        if (el.shadowRoot) cleanEmptyWelcomeOutlines(el.shadowRoot);
                        if (!el.isConnected || (el.textContent || '').trim()) continue;
                        if (el.querySelector('button,input,textarea,select,[contenteditable],vanna-chat')) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width < Math.min(350,viewport.width*0.55) || r.height < 2 || r.height > 40) continue;
                        if (r.top < viewport.top+95 || r.top > viewport.top+300) continue;
                        const css = getComputedStyle(el);
                        const hasBorder = ['Top','Bottom','Left','Right'].some(side =>
                            parseFloat(css['border'+side+'Width']) > 0 && css['border'+side+'Style'] !== 'none');
                        if (!hasBorder && css.boxShadow === 'none') continue;
                        el.remove();
                    }
                };
                cleanEmptyWelcomeOutlines(chat);
                if (chat.shadowRoot) cleanEmptyWelcomeOutlines(chat.shadowRoot);
                // Hide only the visual Vanna status banner (including its border).
                // Ascend from status text to the first banner-sized ancestor.
                // The composer and question suggestions remain untouched.
                const hideStatusStrip = root => {
                    const textWalker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
                    const nodes=[];
                    let textNode;
                    while((textNode=textWalker.nextNode())){
                        if(/^(Sẵn sàng|Ready|Response complete|Đã hoàn tất phản hồi|Connection failed|Kết nối thất bại)$/i.test((textNode.nodeValue||'').trim())) nodes.push(textNode);
                    }
                    for(const node of nodes){
                        let element=node.parentElement;
                        let candidate=null;
                        for(let depth=0; element && depth<10; depth++,element=element.parentElement){
                            if(element===chat || element===root.host)break;
                            const rect=element.getBoundingClientRect();
                            if(rect.width>=260 && rect.height>=35 && rect.height<=100){
                                // Choose the outermost banner-like wrapper rather than the label.
                                // Never include the input area or interactive controls.
                                if(!element.querySelector('textarea,input,[contenteditable="true"]')){
                                    candidate=element;
                                }
                            }
                            if(rect.height>150)break;
                        }
                        if(candidate){
                            candidate.style.setProperty('display','none','important');
                            candidate.setAttribute('data-mes-hidden-status','true');
                        }
                    }
                    root.querySelectorAll?.('*').forEach(el=>{
                        if(el.shadowRoot)hideStatusStrip(el.shadowRoot);
                    });
                };
                hideStatusStrip(chat);
                if(chat.shadowRoot)hideStatusStrip(chat.shadowRoot);
            };
            const queueLocalization = () => {
                if (queued) return;
                queued = true;
                requestAnimationFrame(localize);
            };
            const observeRoot = root => {
                if (visited.has(root)) return;
                visited.add(root);
                new MutationObserver(queueLocalization).observe(root, {
                    subtree:true,childList:true,characterData:true,attributes:true,
                    attributeFilter:['placeholder','aria-label','title']
                });
            };
            observeRoot(chat);
            queueLocalization();
            customElements.whenDefined('vanna-chat').then(queueLocalization).catch(()=>{});
            // Some Vanna nested widgets render asynchronously without changing the host.
            // A lightweight check also handles their delayed attachment.
            const translationTimer = setInterval(() => {
                if (!chat.isConnected) {clearInterval(translationTimer);return;}
                queueLocalization();
            }, 1500);
        }
        // Keep Vanna inside the application panel without forcing its internal layout
        // to grow whenever a new response or task panel appears.
        const boundChat = () => {
            if (!chat.isConnected) return;
            const shadow = chat.shadowRoot;
            if (!shadow || shadow.querySelector('#mes-chat-bounds')) return;
            const sheet = document.createElement('style');
            sheet.id = 'mes-chat-bounds';
            sheet.textContent = `
              :host { display:block!important; position:relative!important; width:100%!important;
                height:100%!important; max-width:100%!important; min-height:0!important; overflow:hidden!important; }
              #app,.app,.chat-container,.chat-layout,.main-container,.vanna-chat-container,
              .chat-window,.chat-wrapper { max-width:100%!important; max-height:100%!important;
                min-width:0!important; min-height:0!important; box-sizing:border-box!important; }
              .messages,.message-list,.chat-messages,.conversation-messages,
              .messages-container,.chat-history { min-height:0!important; overflow-y:auto!important; }
              /* V64: keep the native Tasks column for EVERY role (same as Customer). */
              .chat-main,.chat-main-content,.chat-container,.chat-layout,
              .chat-window,.chat-wrapper,.messages-container,.chat-history {
                min-width:0!important;flex:1 1 auto!important;
              }
              /* Compact and dock the input at the bottom, leave history scrollable. */
              .chat-main {display:flex!important; flex-direction:column!important;min-height:0!important;}
              .chat-main-content,.messages-container,.chat-history,.chat-messages {
                min-height:0!important;overflow-y:auto!important;
              }
              .chat-input-area {position:sticky!important;bottom:0!important;z-index:6!important;
                flex:0 0 auto!important;margin-top:auto!important;max-width:100%!important;
                padding:8px 12px 10px!important;background:#e7e1d5!important;
                border-top:0!important;box-shadow:none!important;}
              .chat-input-container {box-sizing:border-box!important;min-height:42px!important;
                max-height:90px!important;padding:5px 9px!important;margin:0!important;}
              .chat-input-container textarea,.chat-input-area textarea,
              .chat-input-container input[type="text"] {
                box-sizing:border-box!important;min-height:32px!important;
                max-height:66px!important;padding:6px 9px!important;
                font-size:13px!important;line-height:1.4!important;
              }
              /* V61 – give every layer around composer the same beige color.
                 A white footer/flex spacer previously formed a stripe above the input. */
              .chat-main,.chat-input-area,.chat-input-wrapper,
              .chat-input-section,.chat-footer,.chat-main-content,.chat-history,
              .chat-messages,.messages-container,.conversation-messages,
              .message-list,.chat-content,.chat-body {
                background:#e7e1d5!important;
                background-image:none!important;
              }
              .chat-input-area::before,.chat-input-area::after{
                background:transparent!important;
              }
              /* V62: remove the thin teal divider across the conversation after
                 a message, without changing message bubble borders or send box. */
              .chat-main-content,.chat-history,.chat-messages,.messages-container,
              .conversation-messages,.message-list,.messages,.chat-content,
              .chat-body,.chat-input-area,.chat-footer,.chat-input-section {
                border-top:0!important;
                border-bottom:0!important;
                box-shadow:none!important;
                outline:0!important;
              }
              .chat-main-content > hr,.chat-history > hr,
              .chat-messages > hr,.messages-container > hr {
                display:none!important;
              }
              .mes-role-suggestions,.mes-role-suggestion {display:none!important;}
              /* V16: status bar host is INSIDE vanna-chat's open Shadow DOM. */
              vanna-status-bar { display:none!important; visibility:hidden!important;
                height:0!important; min-height:0!important; max-height:0!important;
                padding:0!important; margin:0!important; border:0!important; }
            `;
            shadow.appendChild(sheet);
            // MES UI refresh is scoped to this Vanna instance's open Shadow DOM.
            // Keep the original Vanna element, tasks sidebar, message handlers and SSE.
            const modern = document.createElement('style');
            modern.id = 'mes-ai-modern-v1';
            modern.textContent = `
              :host { color:#18384c!important; font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif!important; }
              #app,.app,.chat-layout,.chat-container,.chat-main,.chat-main-content,
              .chat-history,.chat-messages,.message-list,.messages,.messages-container,
              .conversation-messages,.chat-content,.chat-body,.chat-window,.chat-wrapper {
                background:#f8fafc!important;background-image:none!important;
              }
              /* Compact brand header and soften its gradient. */
              header,.chat-header,.header,.chat-topbar,.top-bar {
                background:linear-gradient(110deg,#0e777e,#124b64)!important;
                border-bottom:1px solid rgba(255,255,255,.12)!important;
              }
              .chat-header,.chat-topbar { min-height:68px!important;padding:12px 20px!important; }
              /* Keep task/sidebar surface visible, just make it intentional. */
              .task-panel,.tasks-panel,.tasks-sidebar,.task-sidebar,.sidebar,
              .chat-sidebar,.right-panel,.task-list-container {
                background:#f1f5f9!important;border-color:#dfe8ee!important;
              }
              /* Message styling: less saturated, more readable. */
              .message,.chat-message,.message-bubble,.message-content,
              .assistant-message,.ai-message,.user-message {
                line-height:1.65!important;overflow-wrap:anywhere!important;
              }
              .user-message,.user-message .message-bubble,
              .message.user,.message.user .message-content,
              [data-role="user"] .message-bubble,[data-role="user"] .message-content {
                background:linear-gradient(125deg,#075d78,#0c9e9a)!important;
                color:#fff!important;border-radius:18px 18px 6px 18px!important;
                box-shadow:0 4px 13px rgba(7,79,103,.12)!important;
              }
              .assistant-message,.assistant-message .message-bubble,
              .message.assistant,.message.assistant .message-content,
              [data-role="assistant"] .message-bubble,[data-role="assistant"] .message-content {
                background:#fff!important;color:#193d51!important;
                border:1px solid #dde8ef!important;
                border-radius:16px 16px 16px 6px!important;
                box-shadow:0 3px 12px rgba(11,50,74,.045)!important;
              }
              .message-content h1,.message-content h2,.message-content h3,
              .markdown h1,.markdown h2,.markdown h3 {
                color:#123f53!important;font-weight:750!important;line-height:1.3!important;
                margin:14px 0 9px!important;
              }
              .message-content table,.markdown table {border-collapse:collapse!important;width:100%!important;max-width:100%!important;}
              .message-content th,.message-content td,.markdown th,.markdown td {
                border:1px solid #e2eaf0!important;padding:10px 12px!important;text-align:left!important;
              }
              .message-content th,.markdown th {background:#f1f7fa!important;}
              .chat-input-area,.chat-input-wrapper,.chat-input-section,.chat-footer {
                background:#f8fafc!important;border-top:1px solid #e2eaf0!important;
                box-shadow:none!important;padding:12px 18px 14px!important;
              }
              .chat-input-container {
                background:#fff!important;border:1.5px solid #d4e3ea!important;
                border-radius:16px!important;min-height:52px!important;
                box-shadow:0 5px 16px rgba(19,67,89,.06)!important;
                padding:7px 10px!important;
              }
              .chat-input-container:focus-within {border-color:#11a6a5!important;box-shadow:0 0 0 3px rgba(17,166,165,.09)!important;}
              .chat-input-container textarea,.chat-input-area textarea,
              .chat-input-container input[type="text"] {
                background:transparent!important;color:#18384c!important;
                font-size:14px!important;line-height:1.6!important;min-height:36px!important;
              }
              .chat-input-area button,.chat-input-container button {
                border-radius:12px!important;transition:background .18s ease,transform .18s ease!important;
              }
              .chat-input-area button:hover:not(:disabled),.chat-input-container button:hover:not(:disabled){transform:translateY(-1px)!important;}
              .mes-role-suggestions,.mes-role-suggestion{display:none!important;}
            `;
            shadow.appendChild(modern);
            // Phase 13: preserve Vanna native vertical layout and composer docking.
            // Phase 12 forced a one-column grid; that stacked Tasks beneath Chat
            // and moved the composer above the conversation. Use a two-track grid
            // instead, with the (unused) task rail collapsed but still mounted.
            const stable = document.createElement('style');
            stable.id = 'mes-ai-fullwidth-phase13';
            stable.textContent = `
              :host { width:100%!important;height:100%!important;display:block!important;min-height:0!important; }
              .chat-layout,.chat-container {
                grid-template-columns:minmax(0,1fr) 0px!important;
                column-gap:0!important;
                min-width:0!important;
              }
              .chat-main {min-width:0!important;max-width:none!important;}
              .chat-sidebar,.tasks-sidebar,.task-sidebar,.right-panel,
              .task-panel,.tasks-panel,.task-list-container,.tasks-column,
              .task-list-panel,.task-list-sidebar {
                width:0!important;min-width:0!important;max-width:0!important;
                padding:0!important;margin:0!important;border:0!important;
                overflow:hidden!important;visibility:hidden!important;
              }
              .chat-input-area { position:sticky!important; bottom:0!important; margin-top:auto!important; }
              .chat-input-container {width:100%!important;max-width:none!important;}
            `;
            shadow.appendChild(stable);
            // Phase 14: clear visual boundaries and more useful message alignment.
            const polish = document.createElement('style');
            polish.id = 'mes-ai-phase14-polish';
            polish.textContent = `
              :host {background:#f7fafc!important;}
              .chat-header,.chat-topbar,header {
                background:linear-gradient(105deg,#102e45 0%,#135368 100%)!important;
                border-bottom:2px solid #7daabb!important;
              }
              .chat-main,.chat-main-content,.messages-container,.chat-history,
              .chat-messages,.conversation-messages,.message-list,.chat-content,.chat-body {
                background:#f7fafc!important;
              }
              .user-message,.user-message .message-bubble,
              .message.user,.message.user .message-content,
              [data-role="user"] .message-bubble,[data-role="user"] .message-content {
                max-width:min(76%,900px)!important;
                background:linear-gradient(112deg,#064863,#0b8790)!important;
                color:#fff!important;border:1px solid #126f83!important;
                border-radius:16px 16px 5px 16px!important;
              }
              .assistant-message,.assistant-message .message-bubble,
              .message.assistant,.message.assistant .message-content,
              [data-role="assistant"] .message-bubble,[data-role="assistant"] .message-content {
                background:#ffffff!important;color:#153a50!important;
                border:1.5px solid #b5cbd9!important;
                border-left:3px solid #178b92!important;
                border-radius:12px!important;
                box-shadow:0 3px 12px rgba(15,55,80,.075)!important;
              }
              .assistant-message,.message.assistant,[data-role="assistant"] {
                max-width:97%!important;
                margin-left:10px!important;
                margin-right:auto!important;
              }
              .chat-input-area,.chat-input-wrapper,.chat-input-section,.chat-footer {
                background:#f0f5f9!important;
                border-top:1px solid #cfdee8!important;
              }
              .chat-input-container {
                border:1.5px solid #acc8d8!important;
                box-shadow:0 2px 9px rgba(16,54,77,.07)!important;
              }
              /* Do not hide other controls such as the expand button. */
              button[aria-label*="minimize" i],button[title*="minimize" i],
              button[aria-label*="thu nhỏ" i],button[title*="thu nhỏ" i] {
                display:none!important;
              }
            `;
            shadow.appendChild(polish);
            const initialExpand = document.createElement('style');
            initialExpand.id = 'mes-ai-phase19-expanded';
            initialExpand.textContent = `
              :host, #app, .app, .chat-layout, .chat-container, .main-container,
              .chat-window, .chat-wrapper, .chat-main, .chat-main-content,
              .chat-history, .messages-container { width:100%!important;
                max-width:none!important; min-width:0!important; box-sizing:border-box!important; }
              .chat-layout,.chat-container { grid-template-columns:minmax(0,1fr) 0!important; }
              .chat-main {flex:1 1 auto!important;}
              .chat-main-content {flex:1 1 auto!important;}
            `;
            shadow.appendChild(initialExpand);
        };
        boundChat();
        customElements.whenDefined('vanna-chat').then(boundChat).catch(()=>{});
        // V64: The Customer layout is the reference for all roles. No role-specific
        // hiding/resizing of the native Tasks column is performed.
        // Keep the composer aligned to the bottom of the AI card, not floating
        // above an unused internal footer. Preserve Vanna's native submit behavior.
        // Phase 15: Vanna renders some horizontal turn separators inside nested
        // web-component Shadow DOMs. Styles on the outer <vanna-chat> cannot
        // affect those subtrees. Scope the fix to this chat instance only.
        const mesRemoveTurnDividers = () => {
            if (!chat.isConnected || !chat.shadowRoot) return;
            const separatorCSS = `
              hr,[role="separator"],.message-divider,.chat-divider,.conversation-divider,
              .turn-divider,.message-separator,.chat-separator,.conversation-separator,
              .separator-line,.turn-separator,[class*="message-divider"],
              [class*="turn-divider"],[class*="conversation-divider"] {
                display:none!important;height:0!important;min-height:0!important;
                border:0!important;box-shadow:none!important;
                background:transparent!important;margin:0!important;padding:0!important;
              }
              .message-row::before,.message-row::after,
              .message-group::before,.message-group::after,
              .chat-turn::before,.chat-turn::after,
              .conversation-turn::before,.conversation-turn::after {
                border:0!important;
              }
            `;
            const hostRect = chat.getBoundingClientRect();
            if (!hostRect.width || !hostRect.height) return;
            const scan = (root) => {
                if (!root.getElementById?.('mes-ai-phase15-dividers')) {
                    const style = document.createElement('style');
                    style.id = 'mes-ai-phase15-dividers';
                    style.textContent = separatorCSS;
                    root.appendChild(style);
                }
                // Also catch library versions that render the separator as a
                // full-width border on a generic, otherwise empty turn wrapper.
                for (const el of root.querySelectorAll('*')) {
                    if (el.localName === 'style' || el.localName === 'script') continue;
                    if (el.closest?.('header,.chat-header,.chat-topbar,.chat-input-area,.chat-footer')) {
                        if (el.shadowRoot) scan(el.shadowRoot);
                        continue;
                    }
                    const rect = el.getBoundingClientRect();
                    if (rect.width > hostRect.width * 0.68 &&
                        rect.bottom > hostRect.top + 110 &&
                        rect.bottom < hostRect.bottom - 100 && rect.height < hostRect.height * 0.65) {
                        const css = getComputedStyle(el);
                        // The thin turquoise line is a border/shadow on a
                        // full-width message wrapper, not the user bubble.
                        const isLineColor = (color) => {
                            const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
                            if (!m) return false;
                            const r=+m[1], g=+m[2], b=+m[3];
                            return g > r * 1.13 && b > r * 1.13 && g >= 90;
                        };
                        if (parseFloat(css.borderBottomWidth) > 0 &&
                            isLineColor(css.borderBottomColor) &&
                            el.style.getPropertyValue('border-bottom') !== 'none') {
                            el.style.setProperty('border-bottom','none','important');
                        }
                        if (parseFloat(css.borderTopWidth) > 0 &&
                            isLineColor(css.borderTopColor) &&
                            el.style.getPropertyValue('border-top') !== 'none') {
                            el.style.setProperty('border-top','none','important');
                        }
                    }
                    if (el.shadowRoot) scan(el.shadowRoot);
                }
            };
            scan(chat.shadowRoot);
        };
        // Phase 19: initialize Vanna in its expanded state, *before* first
        // question. The vendor component may render its header asynchronously.
        // Trigger the same action as the user's Expand control exactly once.
        let mesExpandedOnInit = false;
        const expandVannaAtStart = () => {
            if (mesExpandedOnInit || !chat.isConnected || !chat.shadowRoot) return;
            const view = mount.closest('.chat-area');
            if (!view || view.classList.contains('hidden')) return;
            const scan = (root) => {
                for (const header of root.querySelectorAll('header,.chat-header,.chat-topbar,.header')) {
                    const buttons = [...header.querySelectorAll('button')]
                        .filter(b => !b.closest('.chat-input-area') && getComputedStyle(b).display !== 'none');
                    const expand = buttons.find(b => /maximi[sz]e|expand|full.?screen|phóng to|mở rộng/i.test(
                        [b.getAttribute('aria-label'),b.getAttribute('title'),b.getAttribute('data-tooltip')].join(' ')));
                    // Older Vanna builds expose two header actions without labels:
                    // the first is Minimize and the second is Expand.
                    const rawButtons = [...header.querySelectorAll('button')]
                        .filter(b => !b.closest('.chat-input-area'));
                    const target = expand || (rawButtons.length === 2 ? rawButtons[1] : null);
                    if (target && target.getAttribute('aria-pressed') !== 'true'
                        && getComputedStyle(target).display !== 'none') {
                        mesExpandedOnInit = true;
                        target.click();
                        return true;
                    }
                }
                for (const el of root.querySelectorAll('*')) {
                    if (el.shadowRoot && scan(el.shadowRoot)) return true;
                }
                return false;
            };
            scan(chat.shadowRoot);
        };
        const dockAIComposer = () => {
            if (!chat.shadowRoot || !chat.isConnected) return;
            const composer = chat.shadowRoot.querySelector('.chat-input-container');
            if (!composer) return;
            const area = composer.closest('.chat-input-area') || composer.parentElement;
            if (area) {
                area.dataset.mesDockShift = '0';
                area.style.setProperty('transform', 'none', 'important');
            }
            composer.style.setProperty('width', '100%', 'important');
            composer.style.setProperty('max-width', 'none', 'important');
            composer.style.setProperty('margin', '0', 'important');
            composer.style.setProperty('min-height', '58px', 'important');
            composer.style.setProperty('max-height', '150px', 'important');
        };
        // Hide only the header collapse/minimize button, never the expand control.
        // The Vanna header lives inside its open Shadow DOM (and may render late).
        const hideVannaMinimizeButton = () => {
            const root = chat.shadowRoot;
            if (!root) return;
            const inspect = (scope) => {
                for (const header of scope.querySelectorAll('header,.chat-header,.chat-topbar,.header')) {
                    const buttons = [...header.querySelectorAll('button')]
                        .filter(button => !button.closest('.chat-input-area'));
                    let target = buttons.find(button => /minimi[sz]e|collapse|thu nhỏ/i.test(
                        (button.getAttribute('aria-label')||'')+' '+(button.getAttribute('title')||'')));
                    if (!target) {
                        target = buttons.find(button => {
                            const txt = (button.textContent||'').trim();
                            if (txt === '−' || txt === '–' || txt === '-') return true;
                            const svg = button.querySelector('svg');
                            if (!svg) return false;
                            const lines = [...svg.querySelectorAll('line,path')];
                            return lines.length === 1 && (
                                (lines[0].tagName.toLowerCase()==='line' &&
                                 lines[0].getAttribute('y1')===lines[0].getAttribute('y2')) ||
                                /M\s*5\s+12\s*[hH]\s*14/i.test(lines[0].getAttribute('d')||'')
                            );
                        });
                    }
                    // Known Vanna layout: two right-hand header icon buttons,
                    // first minimizes and second maximizes. Restrict fallback to 2 buttons.
                    if (!target && buttons.length === 2) target = buttons[0];
                    if (target) {
                        target.style.setProperty('display','none','important');
                        target.setAttribute('aria-hidden','true');
                        target.tabIndex = -1;
                    }
                }
                scope.querySelectorAll('*').forEach(el => {if (el.shadowRoot) inspect(el.shadowRoot);});
            };
            inspect(root);
        };
        let aiLayoutQueued=false;
        const refreshAILayout=()=>{
            if(aiLayoutQueued)return;
            aiLayoutQueued=true;
            requestAnimationFrame(()=>{
                aiLayoutQueued=false;
                dockAIComposer();
                expandVannaAtStart();
                hideVannaMinimizeButton();
                mesRemoveTurnDividers();
            });
        };
        const observeAILayout=()=>{
            if(!chat.shadowRoot || chat.dataset.mesAILayoutObserver==='1')return;
            chat.dataset.mesAILayoutObserver='1';
            const observer=new MutationObserver(refreshAILayout);
            observer.observe(chat.shadowRoot,{childList:true,subtree:true});
            refreshAILayout();
        };
        observeAILayout();
        customElements.whenDefined('vanna-chat').then(observeAILayout).catch(()=>{});
        // Nested custom elements may finish rendering after the outer observer fires.
        const layoutTimer=setInterval(()=>{
            if(!chat.isConnected){clearInterval(layoutTimer);return;}
            refreshAILayout();
        },1600);
        window.addEventListener('resize',refreshAILayout);
        // V56: Do not create or move suggested-question bars into the composer.
        // Clear any leftover DOM created by a previous hot-loaded version.
        chat.shadowRoot?.querySelectorAll('.mes-role-suggestions').forEach(el => el.remove());
        const mountObserver = new MutationObserver(boundChat);
        mountObserver.observe(chat,{childList:true,subtree:false});
    }

    function showView(view) {
        if (view === 'employees' && window.currentUser && window.currentUser.role !== 'admin') view = 'dashboard';
        if (view === 'customers' && window.currentUser && !['admin','team_lead'].includes(window.currentUser.role)) view = 'dashboard';
        if (window.currentUser?.role === 'customer') {
            if(view === 'orders') view='dashboard';
            if(view === 'chat') view='customerChat';
            if(!['dashboard','customerChat'].includes(view)) view='dashboard';
        }
        const views = {orders:'ordersView', customerChat:'customerChatView', dashboard:'dashboardView', chat:'chatView', employees:'employeesView', customers:(window.currentUser?.role === 'team_lead' ? 'leadCustomerView' : 'customersView'),  work:'workView'};
        if (!views[view] || !document.getElementById(views[view])) {
            console.error('Missing page section:', view, views[view]);
            return;
        }
        // Nhấn lại menu đang mở (lần thứ hai, không giới hạn 650ms):
        // tải lại dữ liệu ngay tại trang đó, không đổi view hay reset toàn bộ app.
        if (view === currentView && !document.getElementById(views[view]).classList.contains('hidden')) {
            refreshCurrentView();
            return;
        }
        if (view === 'chat' || view === 'customerChat') ensureInternalAI();
        // Change the title first so a failure in page data loading cannot leave a stale title.
        updateTopbar(view);
        for (const [key, id] of Object.entries(views)) {
            const section = document.getElementById(id);
            if (section) section.classList.toggle('hidden', key !== view);
        }
        ['Orders','Dashboard','Chat','Employees','Customers','Attendance','Work'].forEach(name => {
            document.getElementById('tab' + name)?.classList.toggle('active', name.toLowerCase() === view);
        });
        // Desktop: giữ nguyên sidebar khi chuyển tab. Mobile: đóng để nhường không gian.
        if (window.innerWidth <= 800) toggleSideNav(false);
        else toggleSideNav(true);
        try {
            if (view === 'orders') loadCustomerOrders();
            else if (view === 'dashboard') refreshCurrentView();
            else if (view === 'employees') loadEmployees();
            else if (view === 'customers') (window.currentUser?.role === 'team_lead' ? loadCustomerOrders() : loadCustomers());
            

            else if (view === 'work') {
                if (typeof loadWork !== 'function') throw new Error('Không tải được work.js');
                Promise.resolve(loadWork()).catch(e => {
                    console.error('Work page:', e);
                    const out = document.getElementById('workError');
                    if (out) {out.textContent = 'Không tải được công việc: ' + e.message;out.style.color='#b91c1c';}
                });
            }
        } catch(e) {
            console.error('Page navigation:', e);
            if (view === 'work') {
                const out = document.getElementById('workError');
                if (out) {out.textContent='Lỗi mở trang: '+e.message;out.style.color='#b91c1c';}
            }
        }
    }

    function statusBadge(value) {
        const text = String(value ?? '').trim();
        if (!text) return '—';
        const k = text.toLowerCase();
        let cls = 'pill-off';
        if (/^(đang làm|có mặt|active|present)/.test(k)) cls = 'pill-ok';
        else if (/(muộn|late|nghỉ phép|phép|leave)/.test(k)) cls = 'pill-warn';
        else if (/(vắng|absent)/.test(k)) cls = 'pill-bad';
        return `<span class="pill ${cls}">${safeText(text)}</span>`;
    }
 
    function safeText(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    }
    function displayDate(value) { return value ? new Date(value).toLocaleDateString('vi-VN') : '—'; }
    function displayTime(value) { return value ? new Date(value).toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'}) : '—'; }
    const statusLoaded = {};
    async function fillStatusSelect(selectId, url, listUrl, field) {
        const sel = document.getElementById(selectId);
        if (!sel || statusLoaded[selectId]) return;
        let values = null;
        try {
            const res = await fetch(url);
            if (res.ok) values = await res.json();
        } catch (e) {}
        if (!Array.isArray(values)) {
            try {
                const res = await fetch(listUrl);
                if (res.ok) values = [...new Set((await res.json()).map(r => r[field]).filter(Boolean))].sort();
            } catch (e) {}
        }
        if (!Array.isArray(values)) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Tất cả trạng thái</option>' + values.map(v => `<option value="${safeText(v)}">${safeText(v)}</option>`).join('');
        sel.value = values.includes(current) ? current : '';
        statusLoaded[selectId] = true;
    }


// ===== Nhân viên và Chấm công =====
    async function loadEmployees() {
        const body = document.getElementById('employeeTable'); if (!body) return;
        await fillStatusSelect('employeeStatus', '/api/employees/statuses', '/api/employees', 'employment_status');
        body.innerHTML = '<tr><td colspan="8" class="empty">Đang tải dữ liệu...</td></tr>';
        try {
            const params = new URLSearchParams({q:document.getElementById('employeeSearch')?.value || '', status:document.getElementById('employeeStatus')?.value || ''});
            const res = await fetch('/api/employees?' + params); if (!res.ok) throw new Error(await res.text());
            const fetchedRows = await res.json();
            const rows = [...fetchedRows].sort((left,right)=>{
                const rank=position=>/tổ trưởng/i.test(position||'')?0:/kỹ thuật/i.test(position||'')?1:2;
                return rank(left.position)-rank(right.position)
                    || String(left.employee_name||'').localeCompare(String(right.employee_name||''),'vi');
            });
            body.innerHTML = rows.length ? rows.map(r => `<tr><td>${safeText(r.employee_code)}</td><td>${safeText(r.employee_name)}</td><td>${safeText(r.workshop_name || '—')}</td><td>${safeText(r.position || '—')}</td><td>${safeText(r.gender || '—')}</td><td>${displayDate(r.hire_date)}</td><td>${statusBadge(r.employment_status)}</td><td><button type="button" class="work-small-btn" onclick="${/tổ trưởng/i.test(r.position||'')?'showLeadActivity':'showStaffHistory'}(${Number(r.id)})">${/tổ trưởng/i.test(r.position||'')?'Công việc đã giao':'Công việc được giao'}</button></td></tr>`).join('') : '<tr><td colspan="8" class="empty">Không có nhân viên phù hợp.</td></tr>';
            if (typeof setMesTenRowScroll === 'function') setMesTenRowScroll(document.getElementById('employeeTableScroll'));
        } catch (e) { body.innerHTML = `<tr><td colspan="8" class="empty">Không tải được danh sách nhân viên: ${safeText(e.message)}</td></tr>`; }
    }


// ===== Dashboard sản xuất =====
    function fmt(n) { return Number(n || 0).toLocaleString('vi-VN'); }
    function statusPill(status) {
        const cls = status === 'Completed' ? 'pill-complete' : status === 'Planned' ? 'pill-planned' : status === 'Cancelled' ? 'pill-planned' : 'pill-progress';
        const text = status === 'Completed' ? 'Hoàn thành' : status === 'Planned' ? 'Kế hoạch' : status === 'Cancelled' ? 'Đã hủy' : 'Đang sản xuất';
        return `<span class="pill ${cls}">${text}</span>`;
    }
 
    let dashboardRequestSeq = 0;
    async function dashboardFetch(url) {
        // Không để Dashboard quay "Đang tải" vô hạn nếu backend chậm hoặc bị treo.
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 15000);
        try { return await fetch(url, {signal: controller.signal, cache: 'no-store'}); }
        finally { clearTimeout(timer); }
    }
    async function loadDashboard() {
        if (window.currentUser?.role === 'customer') return loadCustomerOrders();
        const requestSeq = ++dashboardRequestSeq;
        try {
            const [summaryRes, poRes] = await Promise.all([dashboardFetch('/api/dashboard/summary'), dashboardFetch('/api/dashboard/pos')]);
            if (requestSeq !== dashboardRequestSeq) return;
            if (!summaryRes.ok || !poRes.ok) throw new Error('Dashboard API chưa sẵn sàng');
            const summary = await summaryRes.json();
            dashboardPOs = (await poRes.json()).filter(p => {
                const st=String(p.status||'').trim().toLowerCase();
                return !['completed','complete','hoàn thành','finished'].includes(st);
            });
            // Trả bảng PO và KPI trước; không chờ API phụ danh sách máy.
            // Khi API phân công máy tải xong mới cập nhật chip máy trên bảng.
            if (window.currentUser?.role === 'admin') {
                dashboardFetch('/api/production-orders/assignments')
                    .then(async res => {
                        if (!res.ok) return;
                        const allocated = await res.json();
                        if (requestSeq !== dashboardRequestSeq || !Array.isArray(allocated)) return;
                        const grouped = new Map();
                        for (const a of allocated) {
                            if (!grouped.has(a.order_code)) grouped.set(a.order_code, []);
                            grouped.get(a.order_code).push({machine_code:a.machine_code,machine_name:a.machine_name});
                        }
                        for (const p of dashboardPOs) {
                            if (grouped.has(p.order_code)) p.machines = grouped.get(p.order_code);
                        }
                        filterPOs();
                    })
                    .catch(e => console.warn('Không tải được phân công máy:', e.message));
            }
            poUpdateAdminUI();
            document.getElementById('mTotal').textContent = fmt(summary.total_po);
            document.getElementById('mTotalSub').textContent = `${fmt(summary.completed)} hoàn thành • ${fmt(summary.planned)} kế hoạch`;
            document.getElementById('mProgress').textContent = fmt(summary.in_progress);
            document.getElementById('mPlanned').textContent = fmt(summary.planned_quantity);
            document.getElementById('mCompletion').textContent = `${Math.min(100, Math.max(0, Number(summary.completion_percent || 0))).toFixed(2)}%`;
            document.getElementById('mActual').textContent = `Sản lượng thực tế cuối dây chuyền: ${fmt(summary.actual_quantity)}`;
            filterPOs();
            if (dashboardPOs.length) {
                loadDashboardPriority(dashboardPOs[0].order_code);
            } else {
                renderDashboardPriority([]);
            }
            const hasSelectedPO = selectedPOCode && dashboardPOs.some(x => x.order_code === selectedPOCode);
            const priorityPO = hasSelectedPO ? selectedPOCode : (dashboardPOs[0] ? dashboardPOs[0].order_code : null);
 
            if (!hasSelectedPO) {
                selectedPOCode = null;
                try {
                    localStorage.removeItem('selectedPOCode');
                } catch (e) {}
            }
 
            if (priorityPO) {
                loadPO(priorityPO, false, false);
            }
        } catch (e) {
            if (requestSeq !== dashboardRequestSeq) return;
            console.error('Không tải được Dashboard:', e);
            const table = document.getElementById('poTable');
            if (table) table.innerHTML = `<tr><td colspan="8" class="empty">Không tải được Dashboard (${e.name === 'AbortError' ? 'API phản hồi quá 15 giây' : 'lỗi API/kết nối'}). Kiểm tra kết nối máy chủ và thử mở lại trang.</td></tr>`;
        }
    }
 
    async function loadSelectedPO() {
        try {
            if (selectedPOCode) {
                await loadPO(selectedPOCode);
            } else if (dashboardPOs.length) {
                selectedPOCode = dashboardPOs[0].order_code;
                await loadPO(selectedPOCode);
            }
        } catch (e) {
            console.error('Không thể cập nhật PO:', e);
        }
    }
 
    function filterPOs() {
        const q = document.getElementById('poSearch').value.trim().toLowerCase();
        const wf=document.getElementById('poWorkshopFilter')?.value||'';
        const sf=document.getElementById('poStatusFilter')?.value||'';
        renderPOs(dashboardPOs.filter(x => {
            const machines = Array.isArray(x.machines)
                ? x.machines.map(m => `${m.machine_code || ''} ${m.machine_name || ''}`).join(' ')
                : '';
            return String(x.status || '').toLowerCase() !== 'completed' && (!wf || x.workshop_name===wf) && (!sf || x.status===sf) && `${x.order_code} ${x.product_code} ${x.product_name} ${x.workshop_name} ${machines}`
                .toLowerCase().includes(q);
        }));
    }
function renderPOs(rows) {
        const tbody = document.getElementById('poTable');
 
        if (!rows.length || !rows.some(x => !['completed','complete','hoàn thành','finished'].includes(String(x.status||'').trim().toLowerCase()))) {
            tbody.innerHTML =
                '<tr><td colspan="8" class="empty">Không có PO phù hợp.</td></tr>';
            return;
        }
 
        tbody.innerHTML = rows.filter(x => !['completed','complete','hoàn thành','finished'].includes(String(x.status || '').trim().toLowerCase())).map(x => {
            const pct = String(x.status || '').toLowerCase() === 'completed'
                ? 100 : Math.min(100, Math.max(0, Number(x.completion_percent || 0)));
 
            const machines = Array.isArray(x.machines)
                ? x.machines
                : [];
 
            const MAX_CHIPS = 3;
            const chipStyle = 'display:inline-block;padding:2px 7px;margin:1px 3px 1px 0;'
                + 'border-radius:6px;background:#eef2f7;color:#334155;font-size:12px;font-weight:600';
            const machineTitle = machines
                .map(m => `${m.machine_code || ''} — ${m.machine_name || ''}`)
                .join('\n');
            const machineHtml = machines.length
                ? `<div title="${esc(machineTitle)}" style="white-space:nowrap">`
                    + machines.slice(0, MAX_CHIPS).map(m =>
                        `<span style="${chipStyle}">${esc(m.machine_code || '')}</span>`).join('')
                    + (machines.length > MAX_CHIPS
                        ? `<span style="${chipStyle};background:#e2e8f0;color:#64748b">+${machines.length - MAX_CHIPS}</span>`
                        : '')
                    + '</div>'
                : '—';
 
            const defects = Number(x.process_defects || 0);
            const defectLabel = Number(x.record_count || 0) === 0
                ? ''
                : defects > 0
                    ? `<span class="po-quality-warning" title="Tổng lỗi được ghi nhận qua các công đoạn; không phải số sản phẩm lỗi duy nhất">⚠ ${fmt(defects)} lỗi công đoạn</span>`
                    : '<span class="po-quality-muted">Chưa ghi nhận lỗi công đoạn</span>';

            return `<tr class="po-row" onclick="loadPO('${String(x.order_code).replace(/'/g, "\\'")}')">
                <td><strong>${esc(x.order_code)}</strong></td>
                <td>${esc(x.product_code)} — ${esc(x.product_name)}</td>
                <td>${esc(x.workshop_name)}</td>
                <td style="min-width:180px">${machineHtml}</td>
                <td>${fmt(x.planned_quantity)}</td>
                <td>${fmt(x.actual_quantity)}</td>
                <td>
                    <span class="progress"><span style="width:${pct}%"></span></span>
                    ${pct.toFixed(2)}%
                    ${defectLabel ? `<div class="po-quality-info">${defectLabel}</div>` : ''}
                </td>
                <td>${statusPill(x.status)}${window.currentUser?.role==='admin'?`<div class="po-row-quick"><button onclick="event.stopPropagation();poOpenRecordDetails('${esc(x.order_code)}')" title="Xem và chỉnh sửa PO, máy và sản lượng">Chỉnh sửa</button>${x.status==='In Progress'?`<button onclick="event.stopPropagation();poComplete('${esc(x.order_code)}')" title="Xác nhận đóng PO đang sản xuất">✓</button>`:String(x.status||'').trim().toLowerCase()==='planned'?`<button onclick="event.stopPropagation();poStart('${esc(x.order_code)}')" title="Bắt đầu sản xuất sau khi phân công máy">▶ Bắt đầu</button><button onclick="event.stopPropagation();poCancel('${esc(x.order_code)}')" title="Hủy PO kế hoạch">✕</button>`:''}</div>`:''}</td>
            </tr>`;
        }).join('');
    }
    function esc(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
 
    function num(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : 0;
    }
 
 
    function renderDashboardPriority(priorities) {
        const box = document.getElementById('dashboardPriority');
        if (!box) return;
 
        if (!priorities || !priorities.length) {
            box.classList.add('hidden');
            box.innerHTML = '';
            return;
        }
 
        box.innerHTML = `
            <div class="priority-head">
                <h4>🚨 Ưu tiên xử lý hôm nay</h4>
                <span style="font-size:10px;color:#7f1d1d">Ưu tiên theo lỗi → hao hụt → vận hành</span>
            </div>
            <div class="priority-list">
                ${priorities.slice(0,3).map((p, i) => `
                    <div class="priority-item ${p.level}">
                        <div class="priority-title">
                            #${i+1} ${esc(p.title)}
                            <span class="priority-badge ${p.level === 'medium' ? 'medium' : ''}">
                                ${p.level === 'high' ? 'ƯU TIÊN CAO' : 'THEO DÕI'}
                            </span>
                        </div>
                        <div class="priority-reason">${esc(p.reason)}</div>
                    </div>
                `).join('')}
            </div>
            <div style="padding:0 16px 14px;font-size:11px;color:#334155">
                <strong>Quyết định nhanh:</strong> nếu hôm nay chỉ xử lý 1 việc,
                ưu tiên <strong>${esc(priorities[0].title)}</strong>.
            </div>`;
 
        box.classList.remove('hidden');
    }
 
    async function loadDashboardPriority(code) {
        const box = document.getElementById('dashboardPriority');
        if (!box || !code) return;
 
        try {
            const res = await fetch(`/api/dashboard/po/${encodeURIComponent(code)}`);
            if (!res.ok) throw new Error('Không tải được dữ liệu ưu tiên');
 
            const data = await res.json();
            const line = Array.isArray(data.line) ? data.line : [];
            const quality = Array.isArray(data.quality) ? data.quality : [];
            const downtime = Array.isArray(data.downtime) ? data.downtime : [];
 
            const priorities = [];
            const number = value => {
                const n = Number(value);
                return Number.isFinite(n) ? n : 0;
            };
            const format = value => Number(value || 0).toLocaleString('vi-VN');
 
            const topDowntime = downtime.length
                ? downtime.reduce((a, b) =>
                    number(b.downtime_minutes) > number(a.downtime_minutes) ? b : a)
                : null;
 
            const topDefectStage = line.length
                ? line.reduce((a, b) =>
                    number(b.defect_rate) > number(a.defect_rate) ? b : a)
                : null;
 
            const topLossStage = line.length > 1
                ? line.slice(1).reduce((best, r, idx) => {
                    const prev = number(line[idx].quantity_produced);
                    const loss = Math.max(0, prev - number(r.quantity_produced));
                    return loss > best.loss
                        ? {row:r, loss:loss, prev:prev}
                        : best;
                }, {row:null, loss:0, prev:0})
                : {row:null, loss:0, prev:0};
 
            const bottleneck = line.length
                ? line.reduce((a, b) =>
                    number(b.production_minutes) > number(a.production_minutes) ? b : a)
                : null;
 
            if (topDefectStage && number(topDefectStage.quantity_defective) > 0) {
                priorities.push({
                    level:'high',
                    title:`${topDefectStage.process_code} — ${topDefectStage.machine_code}`,
                    reason:`${format(topDefectStage.quantity_defective)} lỗi, tỷ lệ ${number(topDefectStage.defect_rate).toFixed(2)}% (cao nhất).`
                });
            }
 
            const topQuality = quality.length
                ? quality.reduce((a, b) =>
                    number(b.failed_quantity) > number(a.failed_quantity) ? b : a)
                : null;
 
            if (topQuality) {
                const checked = topQuality.inspected_quantity ??
                    topQuality.total_checked ??
                    topQuality.total_quantity ??
                    null;
 
                priorities.push({
                    level:'high',
                    title:`Chất lượng — ${topQuality.defect_type}`,
                    reason:`${format(topQuality.failed_quantity)} lỗi${checked !== null ? ` trên ${format(checked)} sản phẩm kiểm tra` : ''}, tỷ lệ ${number(topQuality.defect_rate).toFixed(2)}%. Cần truy vết nguồn phát sinh.`
                });
            }
 
            if (topLossStage.row && topLossStage.loss > 0) {
                priorities.push({
                    level:'high',
                    title:`Hao hụt ${topLossStage.row.process_code}`,
                    reason:`Giảm ${format(topLossStage.loss)} SP từ ${format(topLossStage.prev)} xuống ${format(topLossStage.row.quantity_produced)}; cần xác minh điểm phát sinh.`
                });
            }
 
            if (bottleneck) {
                priorities.push({
                    level:'medium',
                    title:`${bottleneck.process_code} — công đoạn lâu nhất`,
                    reason:`${format(bottleneck.production_minutes)} phút, cao nhất trong dây chuyền; theo dõi thời gian chờ/chu kỳ.`
                });
            }
 
            if (topDowntime) {
                priorities.push({
                    level:'medium',
                    title:`Downtime — ${topDowntime.machine_code}`,
                    reason:`${format(topDowntime.downtime_minutes)} phút, cao nhất; nguyên nhân: ${topDowntime.reason || 'Không rõ'}.`
                });
            }
 
            renderDashboardPriority(priorities.slice(0,3));

        } catch (e) {
            console.error('Không tải được ưu tiên Dashboard:', e);
        }
    }
 
    function apModal(title, body, onSubmit, confirmLabel='Xác nhận') {
        const overlay=document.createElement('div');
        overlay.className='ap-modal-overlay';
        overlay.innerHTML=`<div class="ap-modal" role="dialog" aria-modal="true" aria-labelledby="apModalTitle">
            <div class="ap-modal-head"><h3 id="apModalTitle">${esc(title)}</h3><button type="button" class="ap-modal-close" aria-label="Đóng">✕</button></div>
            <div class="ap-modal-body">${body}</div>
            <div class="ap-modal-footer"><span class="ap-modal-error" role="alert"></span><button type="button" class="ap-modal-close">${onSubmit ? "Hủy" : "Đóng"}</button>${onSubmit?`<button type="button" class="ap-modal-save">${esc(confirmLabel)}</button>`:''}</div>
        </div>`;
        document.body.appendChild(overlay);
        const close=()=>overlay.remove();
        overlay.querySelectorAll('.ap-modal-close').forEach(b=>b.addEventListener('click',close));
        overlay.addEventListener('click',e=>{ if(e.target===overlay)close(); });
        if (onSubmit) overlay.querySelector('.ap-modal-save').addEventListener('click',async e=>{
            e.currentTarget.disabled=true;
            try { const finished=await onSubmit(overlay); if(finished!==false) close(); }
            catch(err) { overlay.querySelector('.ap-modal-error').textContent=typeof err?.message==='string'?err.message:'Không thể xử lý yêu cầu'; }
            finally { if(overlay.isConnected)e.currentTarget.disabled=false; }
        });
        return overlay;
    }
    async function apRequest(url,method='GET',body) {
        // Truy vấn API nghiệp vụ, không sử dụng dữ liệu GET đã cache.
        const opts={method,headers:{},cache:'no-store',credentials:'same-origin'};
        if(body!==undefined){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(body);}
        const res=await fetch(url,opts);
        if(!res.ok){
            const err=await res.json().catch(()=>({}));
            const detail=err.detail;
            const message=Array.isArray(detail)
                ? detail.map(e=>`${(e.loc||[]).filter(v=>v!=='body').join(' → ')||'Dữ liệu'}: ${e.msg||'không hợp lệ'}`).join('; ')
                : (typeof detail==='string'?detail:`API lỗi ${res.status}`);
            throw Error(message);
        }
        return res.json();
    }
    function setDashboardDetailMode(showDetail) {
        const root = document.querySelector('#dashboardView > .dashboard');
        if (!root) return;
 
        const elements = [
            root.querySelector('.dash-head'),
            root.querySelector('.cards'),
            Array.from(root.querySelectorAll('.panel')).find(el => el.querySelector('#poTable')),
            root.querySelector('#dashboardPriority'),
            root.querySelector('#execPanel'),
        ];
 
        elements.forEach(el => {
            if (el) el.classList.toggle('hidden', showDetail);
        });
    }
 
    async function loadPO(code, openDetail = true, selectPO = true) {
        try {
            if (selectPO) {
                saveSelectedPO(code);
            }
            const res = await fetch(`/api/dashboard/po/${encodeURIComponent(code)}`);
            if (!res.ok) throw new Error('PO not found');
 
            const data = await res.json();
            const o = data.order || {};
            const line = Array.isArray(data.line) ? data.line : [];
            const quality = Array.isArray(data.quality) ? data.quality : [];
            const downtime = Array.isArray(data.downtime) ? data.downtime : [];
 
            const analysis = data.analysis || {};
            const finalQty = num(analysis.final_process_quantity ?? (line.length ? line[line.length - 1].quantity_produced : 0));
            const firstQty = num(analysis.first_process_quantity ?? (line.length ? line[0].quantity_produced : 0));
            const plannedQty = num(o.planned_quantity);
            const pct = String(o.status || '').toLowerCase() === 'completed'
                ? 100 : Math.min(100, Math.max(0, num(analysis.completion_percent ?? (plannedQty ? (100 * finalQty / plannedQty) : 0))));
            const loss = num(analysis.total_loss ?? Math.max(0, firstQty - finalQty));
            const lossPct = num(analysis.loss_percent ?? (firstQty ? (100 * loss / firstQty) : 0));
 
            document.getElementById('detailTitle').textContent =
                `Chỉnh sửa ${o.order_code || code}`;
 
            document.getElementById('detailInfo').innerHTML = [
                ['Mã PO', esc(o.order_code || code)],
                ['Sản phẩm', `${esc(o.product_code || '—')} — ${esc(o.product_name || '—')}`],
                ['Xưởng', esc(o.workshop_name || '—')],
                ['Kế hoạch', fmt(plannedQty)],
                ['Đầu dây chuyền', fmt(firstQty)],
                ['Cuối dây chuyền', fmt(finalQty)],
                ['Tiến độ', `${pct.toFixed(2)}%`],
                ['Trạng thái', statusPill(o.status)],
                ['Actual start', o.actual_start ? new Date(o.actual_start).toLocaleString('vi-VN') : '—'],
                ['Actual end', o.actual_end ? new Date(o.actual_end).toLocaleString('vi-VN') : 'Chưa kết thúc']
            ].map(([a,b]) =>
                `<div class="info-item"><label>${a}</label><strong>${b}</strong></div>`
            ).join('');
 
            document.getElementById('lineTable').innerHTML = line.length
                ? line.map((r, i) => {
                    const defectRate = num(r.defect_rate);
                    const isWorst = line.every(x => defectRate >= num(x.defect_rate));
                    return `<tr>
                        <td><strong>${esc(r.process_order ?? i + 1)}. ${esc(r.process_name)}</strong><br>
                            <span style="color:#94a3b8">${esc(r.process_code)}</span></td>
                        <td>${esc(r.machine_code)}<br>
                            <span style="color:#94a3b8">${esc(r.machine_name)}</span></td>
                        <td>${fmt(r.quantity_produced)}</td>
                        <td>${fmt(r.quantity_defective)}</td>
                        <td><strong>${defectRate.toFixed(2)}%</strong>${isWorst && defectRate > 0 ? ' ⚠️' : ''}</td>
                        <td>${fmt(r.production_minutes)} phút</td>
                    </tr>`;
                }).join('')
                : '<tr><td colspan="6" class="empty">Chưa có dữ liệu dây chuyền.</td></tr>';
 
            document.getElementById('qualityBox').innerHTML = quality.length
                ? `<div class="detail-section">
                    <h4>Chất lượng</h4>
                    ${quality.map(q => `
                        <div style="display:flex;justify-content:space-between;font-size:11px;margin-top:8px;gap:12px">
                            <span>${esc(q.defect_type)}</span>
                            <strong>${fmt(q.failed_quantity)} lỗi • ${num(q.defect_rate).toFixed(2)}%</strong>
                        </div>`).join('')}
                   </div>`
                : `<div class="detail-section"><div class="empty">Chưa có dữ liệu lỗi chất lượng.</div></div>`;
 
            document.getElementById('lossBox').innerHTML = `
                <div class="detail-section">
                    <h4>Hao hụt dây chuyền</h4>
                    <div style="display:flex;gap:20px;flex-wrap:wrap;font-size:12px">
                        <span><strong>${fmt(loss)}</strong> sản phẩm</span>
                        <span><strong>${lossPct.toFixed(2)}%</strong> từ đầu đến cuối dây chuyền</span>
                    </div>
                </div>`;
 
            document.getElementById('downtimeBox').innerHTML = downtime.length
                ? `<div class="detail-section">
                    <h4>Downtime của PO</h4>
                    <div class="ok-box">
                        ✓ Downtime được backend trả về với liên kết trực tiếp tới PO.
                        Các số liệu dưới đây được xem là downtime của PO đang phân tích.
                    </div>
                    <div class="table-wrap" style="margin-top:10px">
                        <table>
                            <thead><tr><th>Máy</th><th>Công đoạn</th><th>Downtime</th><th>Nguyên nhân</th></tr></thead>
                            <tbody>
                                ${downtime.map(d => `<tr>
                                    <td>${esc(d.machine_code)}<br><span style="color:#94a3b8">${esc(d.machine_name)}</span></td>
                                    <td>${esc(d.process_code || d.process_name || '—')}</td>
                                    <td>${fmt(d.downtime_minutes)} phút</td>
                                    <td>${esc(d.reason || 'Không rõ')}</td>
                                </tr>`).join('')}
                            </tbody>
                        </table>
                    </div>
                   </div>`
                : `<div class="detail-section">
                    <h4>Downtime</h4>
                    <div class="warning-box">
                        ⚠️ Chưa có dữ liệu downtime được liên kết với ${esc(code)}.
                    </div>
                   </div>`;
 
            const worst = analysis.attention_process || null;
            const recommendations = Array.isArray(analysis.recommendations) ? analysis.recommendations : [];
            const limitations = Array.isArray(analysis.data_limitations) ? analysis.data_limitations : [];
 
            const totalDefects = line.reduce((s, r) => s + num(r.quantity_defective), 0);
            const totalMinutes = line.reduce((s, r) => s + num(r.production_minutes), 0);
            const yieldPct = firstQty ? (100 * finalQty / firstQty) : 0;
            const bottleneck = line.length
                ? line.reduce((a,b) => num(b.production_minutes) > num(a.production_minutes) ? b : a)
                : null;
            const topDowntime = downtime.length
                ? downtime.reduce((a,b) => num(b.downtime_minutes) > num(a.downtime_minutes) ? b : a)
                : null;
            const topDefectStage = line.length
                ? line.reduce((a,b) => num(b.defect_rate) > num(a.defect_rate) ? b : a)
                : null;
            const topLossStage = line.length > 1
                ? line.slice(1).reduce((best, r, idx) => {
                    const prev = num(line[idx].quantity_produced);
                    const lossHere = Math.max(0, prev - num(r.quantity_produced));
                    return lossHere > best.loss ? { row:r, loss:lossHere, prev } : best;
                }, {row:null, loss:0, prev:0})
                : {row:null, loss:0, prev:firstQty};
 
            const priorities = [];
 
            if (topDefectStage && num(topDefectStage.quantity_defective) > 0) {
                const dtText = topDowntime &&
                    String(topDefectStage.machine_code || '') === String(topDowntime.machine_code || '')
                    ? ` Đồng thời ${fmt(topDowntime.downtime_minutes)} phút downtime tại ${topDowntime.machine_code}, nguyên nhân: ${topDowntime.reason || 'Không rõ'}.`
                    : '';
                const lossText = topLossStage.row &&
                    String(topLossStage.row.process_code || '') === String(topDefectStage.process_code || '') &&
                    topLossStage.loss > 0
                    ? ` Hao hụt tại bước này: ${fmt(topLossStage.loss)} SP.`
                    : '';
                priorities.push({
                    level:'high',
                    title:`${topDefectStage.process_code} — ${topDefectStage.machine_code}`,
                    reason:`${fmt(topDefectStage.quantity_defective)} lỗi, tỷ lệ ${num(topDefectStage.defect_rate).toFixed(2)}% (cao nhất).${lossText}${dtText}`
                });
            }
 
            const topQuality = quality.length
                ? quality.reduce((a,b) => num(b.failed_quantity) > num(a.failed_quantity) ? b : a)
                : null;
            if (topQuality) {
                const checked = topQuality.inspected_quantity ?? topQuality.total_checked ?? topQuality.total_quantity ?? null;
                priorities.push({
                    level:'high',
                    title:`Chất lượng — ${topQuality.defect_type}`,
                    reason:`${fmt(topQuality.failed_quantity)} lỗi${checked !== null ? ` trên ${fmt(checked)} sản phẩm kiểm tra` : ''}, tỷ lệ ${num(topQuality.defect_rate).toFixed(2)}%. Cần truy vết nguồn phát sinh.`
                });
            }
 
            if (topLossStage.row && topLossStage.loss > 0) {
                priorities.push({
                    level:'high',
                    title:`Hao hụt ${topLossStage.row.process_code}`,
                    reason:`Giảm ${fmt(topLossStage.loss)} SP từ ${fmt(topLossStage.prev)} xuống ${fmt(topLossStage.row.quantity_produced)}; cần xác minh điểm phát sinh.`
                });
            }
 
            if (bottleneck) {
                priorities.push({
                    level:'medium',
                    title:`${bottleneck.process_code} — công đoạn lâu nhất`,
                    reason:`${fmt(bottleneck.production_minutes)} phút, cao nhất trong dây chuyền; theo dõi thời gian chờ/chu kỳ.`
                });
            }
 
            if (topDowntime) {
                priorities.push({
                    level:'medium',
                    title:`Downtime — ${topDowntime.machine_code}`,
                    reason:`${fmt(topDowntime.downtime_minutes)} phút, cao nhất; nguyên nhân ghi nhận: ${topDowntime.reason || 'Không rõ'}. Theo dõi xử lý vận hành.`
                });
            }
 
            renderDashboardPriority(priorities.slice(0,3));
            document.getElementById('execPanel').classList.remove('hidden');
            document.getElementById('execBody').innerHTML = `
                <div class="exec-grid">
                    <div class="exec-card"><div class="label">Sản lượng cuối</div><div class="value">${fmt(finalQty)}</div><div class="sub">/ ${fmt(plannedQty)} kế hoạch</div></div>
                    <div class="exec-card"><div class="label">Yield dây chuyền</div><div class="value">${yieldPct.toFixed(2)}%</div><div class="sub">Đầu → cuối dây chuyền</div></div>
                    <div class="exec-card"><div class="label">Lỗi công đoạn ghi nhận</div><div class="value">${fmt(totalDefects)}</div><div class="sub">Tổng quantity_defective; không cộng vào hao hụt</div></div>
                    <div class="exec-card"><div class="label">Hao hụt đầu → cuối</div><div class="value">${lossPct.toFixed(2)}%</div><div class="sub">${fmt(loss)} SP trên ${fmt(firstQty)} SP đầu vào</div></div>
                    <div class="exec-card"><div class="label">Công đoạn lâu nhất</div><div class="value">${bottleneck ? esc(bottleneck.process_code) : '—'}</div><div class="sub">${bottleneck ? fmt(bottleneck.production_minutes) + ' phút' : 'Chưa có dữ liệu'}</div></div>
                </div>
                <div class="stage-bars">
                    <div style="font-size:11px;font-weight:700">Diễn biến sản lượng theo công đoạn</div>
                    ${line.map((r, i) => {
                        const q = num(r.quantity_produced);
                        const bar = firstQty ? Math.max(0, Math.min(100, 100*q/firstQty)) : 0;
                        const prev = i === 0 ? firstQty : num(line[i-1].quantity_produced);
                        const stageLoss = Math.max(0, prev - q);
                        return `<div class="stage-row">
                            <div><strong>${esc(r.process_code)}</strong> ${esc(r.process_name)}</div>
                            <div class="stage-track"><span style="width:${bar}%"></span></div>
                            <div class="stage-loss">${fmt(stageLoss)} SP</div>
                        </div>`;
                    }).join('')}
                </div>`;
 
            window.currentPOPriorities = priorities.slice(0,3);

 
            document.getElementById('analysisBox').innerHTML = `
                <div class="detail-section">
                    <h4>Phân tích & khuyến nghị</h4>
                    <div class="analysis-grid">
                        <div class="analysis-card">
                            <div class="label">Hoàn thành</div>
                            <div class="value">${pct.toFixed(2)}%</div>
                        </div>
                        <div class="analysis-card">
                            <div class="label">Hao hụt</div>
                            <div class="value">${fmt(loss)} SP</div>
                        </div>
                        <div class="analysis-card">
                            <div class="label">Tỷ lệ hao hụt</div>
                            <div class="value">${lossPct.toFixed(2)}%</div>
                        </div>
                        <div class="analysis-card">
                            <div class="label">Thời gian SX</div>
                            <div class="value">${fmt(analysis.total_production_minutes ?? totalMinutes)} phút</div>
                        </div>
                    </div>
                    ${recommendations.length ? `
                        <div style="margin-top:12px;font-size:11px;font-weight:700">Hành động đề xuất</div>
                        <ul class="recommend-list">
                            ${recommendations.map(x => `<li>${esc(x)}</li>`).join('')}
                        </ul>` : ''}
                    ${limitations.length ? `
                        <div class="analysis-meta"><strong>Giới hạn dữ liệu:</strong> ${limitations.map(x => esc(x)).join(' • ')}</div>` : ''}
                </div>`;
 
            document.getElementById('attentionBox').innerHTML = worst && num(worst.defect_rate) > 0
                ? `<div class="detail-section">
                    <h4>Công đoạn cần chú ý</h4>
                    <div class="danger-box">
                        ⚠️ <strong>${esc(worst.process_name)} (${esc(worst.process_code)})</strong>
                        có tỷ lệ lỗi cao nhất: <strong>${num(worst.defect_rate).toFixed(2)}%</strong>,
                        tương ứng <strong>${fmt(worst.quantity_defective)}</strong> sản phẩm lỗi.
                        ${firstQty ? `Sản lượng đầu dây chuyền ${fmt(firstQty)} → tại công đoạn này ${fmt(worst.quantity_produced)}.` : ''}
                    </div>
                   </div>`
                : `<div class="detail-section">
                    <div class="ok-box">Chưa có dữ liệu đủ để xác định công đoạn cần chú ý.</div>
                   </div>`;
 
            if (openDetail) {
                setDashboardDetailMode(true);
                document.getElementById('detailPanel').classList.remove('hidden');
                document.getElementById('detailPanel').scrollIntoView({behavior:'smooth', block:'start'});
            }
 
        } catch (e) {
            console.error(e);
            alert('Không tải được chi tiết PO. Kiểm tra API /api/dashboard/po/{order_code}.');
        }
    }


