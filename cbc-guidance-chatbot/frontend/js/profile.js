// Profile Management Functions
document.addEventListener('DOMContentLoaded', function() {
    loadProfileData();
    setupProfileForm();
});

// Load current profile data
function loadProfileData() {
    const userId = localStorage.getItem('userId');
    if (!userId) {
        document.getElementById('current-profile-display').innerHTML = '<p>Please log in to view your profile.</p>';
        return;
    }
    
    const profile = getStoredProfile();
    if (profile && Object.keys(profile).length > 0) {
        displayCurrentProfile(profile);
        prefillProfileForm(profile);
    }
}

// Display current profile information
function displayCurrentProfile(profile) {
    const displayDiv = document.getElementById('current-profile-display');
    
    const profileHTML = `
        <div class="profile-item">
            <strong>Name:</strong> ${profile.name || 'Not set'}
        </div>
        <div class="profile-item">
            <strong>Email:</strong> ${profile.email || 'Not set'}
        </div>
        <div class="profile-item">
            <strong>Phone:</strong> ${profile.phone || 'Not set'}
        </div>
        <div class="profile-item">
            <strong>Bio:</strong> ${profile.bio || 'Not set'}
        </div>
        <div class="profile-item">
            <strong>Interests:</strong> ${profile.interests || 'Not set'}
        </div>
        <div class="profile-item">
            <strong>Career Goals:</strong> ${profile.goals || 'Not set'}
        </div>
    `;
    
    displayDiv.innerHTML = profileHTML;
}

// Prefill profile form with current data
function prefillProfileForm(profile) {
    document.getElementById('name').value = profile.name || '';
    document.getElementById('email').value = profile.email || '';
    document.getElementById('phone').value = profile.phone || '';
    document.getElementById('bio').value = profile.bio || '';
    document.getElementById('interests').value = profile.interests || '';
    document.getElementById('goals').value = profile.goals || '';
}

// Setup profile form event listeners
function setupProfileForm() {
    const editBtn = document.getElementById('edit-profile-btn');
    const saveBtn = document.getElementById('save-profile-btn');
    
    editBtn.addEventListener('click', function() {
        enableProfileEditing();
    });
    
    saveBtn.addEventListener('click', function() {
        saveProfileChanges();
    });
}

// Save profile changes
async function saveProfileChanges() {
    const userId = localStorage.getItem('userId');
    if (!userId) {
        alert('Please log in to save profile changes.');
        return;
    }
    
    const profileData = {
        name: document.getElementById('name').value,
        email: document.getElementById('email').value,
        phone: document.getElementById('phone').value,
        bio: document.getElementById('bio').value,
        interests: document.getElementById('interests').value,
        goals: document.getElementById('goals').value
    };
    
    try {
        const response = await fetch(`${API_BASE}/user/profile`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('authToken') || ''}`
            },
            body: JSON.stringify(profileData)
        });
        
        if (response.ok) {
            const updatedProfile = await response.json();
            saveStoredProfile(updatedProfile);
            displayCurrentProfile(updatedProfile);
            alert('Profile updated successfully!');
            
            // Disable editing mode
            document.getElementById('edit-profile-btn').style.display = 'none';
            document.getElementById('save-profile-btn').style.display = 'none';
            document.querySelectorAll('.profile-field').forEach(field => field.setAttribute('disabled', 'disabled'));
        } else {
            alert('Error updating profile. Please try again.');
        }
    } catch (error) {
        console.error('Profile update error:', error);
        alert('Error updating profile. Please try again.');
    }
}
