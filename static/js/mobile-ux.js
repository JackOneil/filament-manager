        document.addEventListener('DOMContentLoaded', () => {
            // Only execute if we are on a mobile screen width
            if (window.innerWidth >= 768) return;

            // 1. Collapsing/Expanding Topbar Header on Scroll
            const mainEl = document.querySelector('main');
            const headerEl = document.querySelector('header');
            if (mainEl && headerEl) {
                let lastScrollTop = 0;
                mainEl.addEventListener('scroll', () => {
                    const scrollTop = mainEl.scrollTop;
                    if (scrollTop > lastScrollTop && scrollTop > 50) {
                        // Scrolling down -> hide header
                        headerEl.classList.add('collapsed');
                    } else {
                        // Scrolling up -> show header
                        headerEl.classList.remove('collapsed');
                    }
                    lastScrollTop = scrollTop;
                }, { passive: true });
            }

            // 2. Horizontal Swipe Gestures for Main Tab Switching
            let touchstartX = 0;
            let touchstartY = 0;
            let touchendX = 0;
            let touchendY = 0;

            const minSwipeDistance = 100; // in px
            const maxSwipeVerticalDeviation = 60; // to prevent horizontal swipe triggering on diagonal/vertical scroll

            const currentEndpoint = window.__helpEndpoint;
            const swipeRoutesEl = document.getElementById('swipe-routes-data');
            let swipeRoutes = {};
            if (swipeRoutesEl) {
                try { swipeRoutes = JSON.parse(swipeRoutesEl.textContent); } catch (e) { /* ignore */ }
            }

            if (currentEndpoint && swipeRoutes[currentEndpoint]) {
                document.addEventListener('touchstart', e => {
                    // Do not trigger swipe on interactive elements, maps, or drag-and-drop handles
                    if (e.target.closest('input, textarea, select, button, a, [role="button"], #map, [draggable="true"], .no-swipe')) return;
                    touchstartX = e.changedTouches[0].screenX;
                    touchstartY = e.changedTouches[0].screenY;
                }, { passive: true });

                document.addEventListener('touchend', e => {
                    if (e.target.closest('input, textarea, select, button, a, [role="button"], #map, [draggable="true"], .no-swipe')) return;
                    touchendX = e.changedTouches[0].screenX;
                    touchendY = e.changedTouches[0].screenY;
                    handleSwipe();
                }, { passive: true });
            }

            function handleSwipe() {
                const diffX = touchendX - touchstartX;
                const diffY = Math.abs(touchendY - touchstartY);

                if (Math.abs(diffX) > minSwipeDistance && diffY < maxSwipeVerticalDeviation) {
                    if (diffX < 0) {
                        // Swiped Left -> Go to Next Tab
                        const nextUrl = swipeRoutes[currentEndpoint].next;
                        if (nextUrl) {
                            window.location.href = nextUrl;
                        }
                    } else {
                        // Swiped Right -> Go to Prev Tab
                        const prevUrl = swipeRoutes[currentEndpoint].prev;
                        if (prevUrl) {
                            window.location.href = prevUrl;
                        }
                    }
                }
            }

            // 3. Pull-to-Refresh functionality on Main Container
            const ptrWrap = document.getElementById('ptr-wrap');
            const ptrIcon = document.getElementById('ptr-icon');
            const ptrText = document.getElementById('ptr-text');
            const ptrLabelPull    = ptrWrap ? (ptrWrap.dataset.pull    || 'Pull down to refresh') : 'Pull down to refresh';
            const ptrLabelRelease = ptrWrap ? (ptrWrap.dataset.release || 'Release to refresh')   : 'Release to refresh';
            const ptrLabelLoading = ptrWrap ? (ptrWrap.dataset.loading || 'Loading...')            : 'Loading...';
            
            if (mainEl && ptrWrap && ptrIcon && ptrText) {
                let startY = 0;
                let active = false;

                mainEl.addEventListener('touchstart', e => {
                    // Only start tracking if the container is scrolled all the way to the top
                    if (mainEl.scrollTop === 0) {
                        startY = e.touches[0].pageY;
                        active = true;
                    }
                }, { passive: true });

                mainEl.addEventListener('touchmove', e => {
                    if (!active || mainEl.scrollTop > 0) return;
                    const currentY = e.touches[0].pageY;
                    const diffY = currentY - startY;

                    if (diffY > 0) {
                        // We are pulling down at the top of the container
                        // Prevent native overscroll bouncing/scrolling where possible
                        if (e.cancelable) e.preventDefault();

                        // Apply resistance
                        const pullHeight = Math.min(diffY * 0.4, 70);
                        ptrWrap.style.height = `${pullHeight}px`;

                        if (pullHeight >= 50) {
                            ptrIcon.style.transform = 'rotate(180deg)';
                            ptrText.innerText = ptrLabelRelease;
                        } else {
                            ptrIcon.style.transform = 'rotate(0deg)';
                            ptrText.innerText = ptrLabelPull;
                        }
                    }
                }, { passive: false });

                mainEl.addEventListener('touchend', () => {
                    if (!active) return;
                    active = false;
                    const currentHeight = parseInt(ptrWrap.style.height || '0');

                    if (currentHeight >= 50) {
                        // Trigger Refresh
                        ptrWrap.style.height = '50px';
                        ptrIcon.className = 'fa-solid fa-spinner fa-spin';
                        ptrIcon.style.transform = 'none';
                        ptrText.innerText = ptrLabelLoading;
                        window.location.reload();
                    } else {
                        // Cancel
                        ptrWrap.style.height = '0px';
                    }
                }, { passive: true });
            }
        });
