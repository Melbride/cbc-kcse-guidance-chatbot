// Responsive Design Handler
class ResponsiveHandler {
    constructor() {
        this.breakpoints = {
            mobile: 480,
            tablet: 768,
            desktop: 1024
        };
        this.init();
    }

    init() {
        this.handleResize();
        window.addEventListener('resize', () => this.handleResize());
        window.addEventListener('load', () => this.handleResize());
    }

    handleResize() {
        const width = window.innerWidth;
        console.log('Window width:', width, 'Applying responsive styles...');
        
        // Remove all responsive classes first
        document.body.classList.remove('mobile-view', 'tablet-view', 'desktop-view');
        
        // Add appropriate class based on screen width
        if (width <= this.breakpoints.mobile) {
            console.log('Applying mobile styles');
            document.body.classList.add('mobile-view');
            this.applyMobileStyles();
        } else if (width <= this.breakpoints.tablet) {
            console.log('Applying tablet styles');
            document.body.classList.add('tablet-view');
            this.applyTabletStyles();
        } else if (width <= this.breakpoints.desktop) {
            console.log('Applying desktop styles');
            document.body.classList.add('desktop-view');
            this.applyDesktopStyles();
        } else {
            console.log('Applying large desktop styles');
            this.applyLargeDesktopStyles();
        }
    }

    applyMobileStyles() {
        // Hero section
        const hero = document.querySelector('.hero');
        const heroContent = document.querySelector('.hero-content');
        const heroTitle = document.querySelector('.hero h1');
        const heroText = document.querySelector('.hero p');
        
        if (hero) {
            hero.style.padding = '1.5rem 0 2rem';
            hero.style.minHeight = 'auto';
        }
        
        if (heroContent) {
            heroContent.style.padding = '0 1rem';
        }
        
        if (heroTitle) {
            heroTitle.style.fontSize = '1.75rem';
        }
        
        if (heroText) {
            heroText.style.fontSize = '0.95rem';
        }

        // Sections
        const sections = document.querySelectorAll('.about, .systems, .cta');
        sections.forEach(section => {
            section.style.padding = '2rem 1rem';
        });

        // Cards - more specific targeting
        const aboutCards = document.querySelectorAll('.about-card');
        const systemCards = document.querySelectorAll('.system-card');
        
        aboutCards.forEach(card => {
            card.style.padding = '1.5rem';
            card.style.margin = '0';
            card.style.width = '100%';
        });
        
        systemCards.forEach(card => {
            card.style.padding = '1.5rem';
            card.style.margin = '0';
            card.style.width = '100%';
        });

        // Grid layouts - force single column
        const aboutGrid = document.querySelector('.about-grid');
        const systemsGrid = document.querySelector('.systems-grid');
        
        if (aboutGrid) {
            aboutGrid.style.display = 'grid';
            aboutGrid.style.gridTemplateColumns = '1fr';
            aboutGrid.style.gap = '1rem';
            aboutGrid.style.width = '100%';
        }
        
        if (systemsGrid) {
            systemsGrid.style.display = 'grid';
            systemsGrid.style.gridTemplateColumns = '1fr';
            systemsGrid.style.gap = '1rem';
            systemsGrid.style.width = '100%';
        }

        // Buttons
        const buttons = document.querySelectorAll('.btn');
        buttons.forEach(btn => {
            btn.style.width = '100%';
            btn.style.padding = '1rem';
            btn.style.textAlign = 'center';
        });

        // Footer
        const footerContainer = document.querySelector('.footer-container');
        const footerSection = document.querySelector('.footer-section');
        const footerTitle = document.querySelector('.footer-section h3');
        const footerText = document.querySelector('.footer-section p');
        
        if (footerContainer) {
            footerContainer.style.padding = '0 1rem';
        }
        
        if (footerTitle) {
            footerTitle.style.fontSize = '1.1rem';
        }
        
        if (footerText) {
            footerText.style.fontSize = '0.75rem';
        }
    }

    applyTabletStyles() {
        // Hero section
        const hero = document.querySelector('.hero');
        const heroContent = document.querySelector('.hero-content');
        const heroTitle = document.querySelector('.hero h1');
        const heroText = document.querySelector('.hero p');
        
        if (hero) {
            hero.style.padding = '2rem 0 3rem';
            hero.style.minHeight = 'auto';
        }
        
        if (heroContent) {
            heroContent.style.padding = '0 1.5rem';
        }
        
        if (heroTitle) {
            heroTitle.style.fontSize = '2rem';
        }
        
        if (heroText) {
            heroText.style.fontSize = '1rem';
        }

        // Sections
        const sections = document.querySelectorAll('.about, .systems, .cta');
        sections.forEach(section => {
            section.style.padding = '3rem 1.5rem';
        });

        // Grid layouts - force single column on tablet
        const aboutGridTablet = document.querySelector('.about-grid');
        const systemsGridTablet = document.querySelector('.systems-grid');
        
        if (aboutGridTablet) {
            aboutGridTablet.style.display = 'grid';
            aboutGridTablet.style.gridTemplateColumns = '1fr';
            aboutGridTablet.style.gap = '1.5rem';
            aboutGridTablet.style.width = '100%';
        }
        
        if (systemsGridTablet) {
            systemsGridTablet.style.display = 'grid';
            systemsGridTablet.style.gridTemplateColumns = '1fr';
            systemsGridTablet.style.gap = '1.5rem';
            systemsGridTablet.style.width = '100%';
        }

        // Footer
        const footerContainer = document.querySelector('.footer-container');
        const footerText = document.querySelector('.footer-section p');
        
        if (footerContainer) {
            footerContainer.style.padding = '0 1.5rem';
        }
        
        if (footerText) {
            footerText.style.fontSize = '0.8rem';
            footerText.style.lineHeight = '1.5';
        }
    }

    applyDesktopStyles() {
        // Reset to desktop styles
        const hero = document.querySelector('.hero');
        const heroContent = document.querySelector('.hero-content');
        const heroTitle = document.querySelector('.hero h1');
        
        if (hero) {
            hero.style.padding = '1rem 0 3rem';
            hero.style.minHeight = '280px';
        }
        
        if (heroContent) {
            heroContent.style.padding = '0 2rem';
        }
        
        if (heroTitle) {
            heroTitle.style.fontSize = '';
        }

        // Footer
        const footerContainer = document.querySelector('.footer-container');
        if (footerContainer) {
            footerContainer.style.maxWidth = '100%';
            footerContainer.style.padding = '0 2rem';
        }
    }

    applyLargeDesktopStyles() {
        // Reset to original desktop styles
        const allElements = document.querySelectorAll('*');
        allElements.forEach(el => {
            // Remove inline styles that were added by responsive handler
            if (el.style.removeProperty) {
                ['padding', 'fontSize', 'width', 'textAlign', 'gridTemplateColumns', 'gap', 'lineHeight', 'minHeight'].forEach(prop => {
                    el.style.removeProperty(prop);
                });
            }
        });
    }
}

// Initialize responsive handler when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new ResponsiveHandler();
});

// Also initialize immediately if DOM is already loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new ResponsiveHandler();
    });
} else {
    new ResponsiveHandler();
}
