// Landing Page Scripts
// Responsive Handler
function handleResponsive() {
    const width = window.innerWidth;
    console.log('Width:', width);
    
    // Force cards to be responsive
    const aboutGrid = document.querySelector('.about-grid');
    const systemsGrid = document.querySelector('.systems-grid');
    const aboutCards = document.querySelectorAll('.about-card');
    const systemCards = document.querySelectorAll('.system-card');
    
    if (width <= 768) {
        console.log('Mobile/Tablet mode - forcing single column');
        
        // Force single column layout
        if (aboutGrid) {
            aboutGrid.style.setProperty('grid-template-columns', '1fr', 'important');
            aboutGrid.style.display = 'grid';
        }
        if (systemsGrid) {
            systemsGrid.style.setProperty('grid-template-columns', '1fr', 'important');
            systemsGrid.style.display = 'grid';
        }
        
        // Make cards full width
        aboutCards.forEach(card => {
            card.style.setProperty('width', '100%', 'important');
            card.style.setProperty('margin', '0', 'important');
        });
        systemCards.forEach(card => {
            card.style.setProperty('width', '100%', 'important');
            card.style.setProperty('margin', '0', 'important');
        });
    } else {
        console.log('Desktop mode - reset to original');
        // Reset to original styles
        if (aboutGrid) aboutGrid.style.gridTemplateColumns = '';
        if (systemsGrid) systemsGrid.style.gridTemplateColumns = '';
        aboutCards.forEach(card => card.style.width = '');
        systemCards.forEach(card => card.style.width = '');
    }
}

// Theme Toggle
function initThemeToggle() {
    console.log('Initializing theme toggle...');
    
    const themeToggle = document.getElementById('themeToggle');
    const moonIcon = document.getElementById('moonIcon');
    const sunIcon = document.getElementById('sunIcon');
    const body = document.body;

    console.log('Elements found:', {
        themeToggle: !!themeToggle,
        moonIcon: !!moonIcon,
        sunIcon: !!sunIcon,
        body: !!body
    });

    if (!themeToggle) {
        console.error('Theme toggle button not found!');
        return;
    }

    // Check for saved theme preference or default to light mode
    const currentTheme = localStorage.getItem('theme') || 'light';
    console.log('Current theme from storage:', currentTheme);
    
    // Apply the correct theme on load
    function applyTheme(theme) {
        console.log('Applying theme:', theme);
        if (theme === 'dark') {
            body.classList.add('dark-mode');
            if (moonIcon) {
                moonIcon.style.display = 'none';
                console.log('Moon icon hidden');
            }
            if (sunIcon) {
                sunIcon.style.display = 'block';
                console.log('Sun icon shown');
            }
        } else {
            body.classList.remove('dark-mode');
            if (moonIcon) {
                moonIcon.style.display = 'block';
                console.log('Moon icon shown');
            }
            if (sunIcon) {
                sunIcon.style.display = 'none';
                console.log('Sun icon hidden');
            }
        }
    }
    
    applyTheme(currentTheme);

    themeToggle.addEventListener('click', (e) => {
        e.preventDefault();
        console.log('Theme toggle clicked!');
        
        const isDark = body.classList.contains('dark-mode');
        const newTheme = isDark ? 'light' : 'dark';
        
        console.log('Switching from', isDark ? 'dark' : 'light', 'to', newTheme);
        
        body.classList.toggle('dark-mode');
        localStorage.setItem('theme', newTheme);
        
        if (moonIcon) moonIcon.style.display = isDark ? 'block' : 'none';
        if (sunIcon) sunIcon.style.display = isDark ? 'none' : 'block';
        
        console.log('Theme switched to:', newTheme);
    });
    
    // Add backup click handler
    themeToggle.onclick = (e) => {
        e.preventDefault();
        console.log('Backup click handler triggered!');
        
        const isDark = body.classList.contains('dark-mode');
        
        if (isDark) {
            body.classList.remove('dark-mode');
            localStorage.setItem('theme', 'light');
            if (moonIcon) moonIcon.style.display = 'block';
            if (sunIcon) sunIcon.style.display = 'none';
            
            // Force light mode colors
            body.style.backgroundColor = '#f5f7f6';
            body.style.color = '#1b4332';
            
            // Update cards
            document.querySelectorAll('.about-card, .system-card').forEach(card => {
                card.style.backgroundColor = '#ffffff';
                card.style.color = '#1b4332';
                card.style.borderColor = '#e0e8e5';
            });
            
            console.log('Backup: Switched to light mode');
        } else {
            body.classList.add('dark-mode');
            localStorage.setItem('theme', 'dark');
            if (moonIcon) moonIcon.style.display = 'none';
            if (sunIcon) sunIcon.style.display = 'block';
            
            // Reset to CSS variables for dark mode
            body.style.backgroundColor = '';
            body.style.color = '';
            
            // Reset cards to CSS variables
            document.querySelectorAll('.about-card, .system-card').forEach(card => {
                card.style.backgroundColor = '';
                card.style.color = '';
                card.style.borderColor = '';
            });
            
            console.log('Backup: Switched to dark mode');
        }
    };
}

// Add hover effects to cards
function addHoverEffects() {
    const cards = document.querySelectorAll('.about-card, .system-card');
    
    cards.forEach(card => {
        card.style.transition = 'transform 0.3s ease, box-shadow 0.3s ease, border-color 0.3s ease';
        
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-8px) scale(1.02)';
            card.style.boxShadow = '0 15px 35px rgba(45, 106, 79, 0.3)';
            card.style.borderColor = '#52b788';
        });
        
        card.addEventListener('mouseleave', () => {
            card.style.transform = 'translateY(0) scale(1)';
            card.style.boxShadow = '0 4px 6px rgba(0, 0, 0, 0.1)';
            card.style.borderColor = '';
        });
    });
}

// Typewriter effect for hero text
function typewriterEffect(element, text, speed = 50) {
    let i = 0;
    element.textContent = '';
    
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }
    
    type();
}

// Button animations
function addButtonAnimations() {
    const buttons = document.querySelectorAll('.btn');
    
    buttons.forEach(btn => {
        btn.style.transition = 'all 0.3s ease';
        btn.style.position = 'relative';
        btn.style.overflow = 'hidden';
        
        // Hover effects
        btn.addEventListener('mouseenter', () => {
            btn.style.transform = 'translateY(-2px)';
            btn.style.boxShadow = '0 8px 20px rgba(0, 0, 0, 0.2)';
        });
        
        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'translateY(0)';
            btn.style.boxShadow = 'none';
        });
        
        // Click ripple effect
        btn.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            ripple.classList.add('ripple');
            
            this.appendChild(ripple);
            
            setTimeout(() => {
                ripple.remove();
            }, 600);
        });
    });
}

// Theme toggle animation
function animateThemeToggle() {
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.style.transition = 'transform 0.3s ease';
        
        themeToggle.addEventListener('click', () => {
            themeToggle.style.transform = 'rotate(180deg)';
            setTimeout(() => {
                themeToggle.style.transform = 'rotate(0deg)';
            }, 300);
        });
    }
}

// Floating elements animation
function addFloatingAnimation() {
    const floatingElements = document.querySelectorAll('.system-card');
    
    floatingElements.forEach((el, index) => {
        el.style.animation = `float ${3 + index * 0.5}s ease-in-out infinite`;
        el.style.animationDelay = `${index * 0.2}s`;
    });
    
    // Add floating keyframes
    const style = document.createElement('style');
    style.textContent = `
        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-10px); }
        }
        @keyframes ripple {
            0% {
                transform: scale(0);
                opacity: 1;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.5);
            }
            100% {
                transform: scale(4);
                opacity: 0;
            }
        }
        .ripple {
            position: absolute;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.5);
            transform: scale(0);
            animation: ripple 0.6s ease-out;
            pointer-events: none;
        }
    `;
    document.head.appendChild(style);
}

// Staggered card reveals
function staggeredReveal() {
    const cards = document.querySelectorAll('.about-card, .system-card');
    
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(50px)';
        card.style.transition = `all 0.6s ease ${index * 0.1}s`;
        
        setTimeout(() => {
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 + index * 100);
    });
}

// Smooth scroll for navigation
function addSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// Add scroll animations
function addScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -10px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0) scale(1)';
            }
        });
    }, observerOptions);
    
    // Observe elements for animation
    const animatedElements = document.querySelectorAll('.about-card, .system-card, .about h3, .systems h2');
    
    animatedElements.forEach((el, index) => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(60px) scale(0.8)';
        el.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
        el.style.transitionDelay = `${index * 0.1}s`;
        observer.observe(el);
    });
}

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing everything...');
    
    // Initialize theme toggle FIRST
    initThemeToggle();
    
    // Initialize responsive handler
    handleResponsive();
    window.addEventListener('resize', handleResponsive);
    
    // Initialize hover effects
    addHoverEffects();
    
    // Initialize all new animations
    addButtonAnimations();
    animateThemeToggle();
    addFloatingAnimation();
    staggeredReveal();
    addSmoothScroll();
    
    // Add typewriter effect to hero title
    const heroTitle = document.querySelector('.hero h1');
    if (heroTitle) {
        const originalText = heroTitle.textContent;
        setTimeout(() => {
            typewriterEffect(heroTitle, originalText, 60);
        }, 500);
    }
    
    // Initialize scroll animations
    setTimeout(() => {
        addScrollAnimations();
    }, 1000);
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        handleResponsive();
        window.addEventListener('resize', handleResponsive);
        initThemeToggle();
    });
} else {
    handleResponsive();
    window.addEventListener('resize', handleResponsive);
    initThemeToggle();
}
