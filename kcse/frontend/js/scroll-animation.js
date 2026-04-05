// Scroll animation for landing page cards
document.addEventListener('DOMContentLoaded', function() {
  const cards = document.querySelectorAll('.landing-card');
  
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  };
  
  const observer = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('animate-in');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);
  
  cards.forEach(card => {
    card.classList.add('animate-on-scroll');
    observer.observe(card);
  });
});
