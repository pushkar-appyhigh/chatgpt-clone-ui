document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const newChatBtn = document.getElementById('new-chat-btn');
    const conversationHistory = document.getElementById('conversation-history');
    const historyPlaceholder = document.getElementById('history-placeholder');
    
    // User authentication elements
    const loginArea = document.getElementById('login-area');
    const userInfo = document.getElementById('user-info');
    const userEmail = document.getElementById('user-email');
    const logoutBtn = document.getElementById('logout-btn');
    const googleLoginBtn = document.getElementById('google-login-btn');
    const loginOverlay = document.getElementById('login-overlay');
    const overlayLoginBtn = document.getElementById('overlay-google-login-btn');
    const clearConversationsBtn = document.getElementById('clear-conversations-btn');
    
    // Modal elements
    const clearModal = document.getElementById('clear-modal');
    const clearConfirmBtn = document.getElementById('clear-confirm-btn');
    const clearCancelBtn = document.getElementById('clear-cancel-btn');
    
    // App state
    let currentConversationId = generateConversationId();
    let conversations = loadConversations();
    let currentUser = null;
    
    // Check for just_logged_out parameter in URL
    const urlParams = new URLSearchParams(window.location.search);
    const justLoggedOut = urlParams.get('just_logged_out');
    
    // Initialize authentication state
    initializeAuthState(justLoggedOut === 'true');
    
    // Auto-resize the textarea as the user types
    chatInput.addEventListener('input', () => {
        chatInput.style.height = 'auto';
        chatInput.style.height = (chatInput.scrollHeight) + 'px';
    });
    
    // Handle command+enter (Mac) or ctrl+enter (Windows/Linux)
    chatInput.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
            e.preventDefault();
            chatForm.dispatchEvent(new Event('submit'));
        }
    });
    
    // Handle form submission for chat
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Check if user is logged in
        if (!currentUser) {
            // Show login overlay if not logged in
            loginOverlay.classList.remove('hidden');
            return;
        }
        
        const message = chatInput.value.trim();
        if (!message) return;
        
        // Clear input field and reset height
        chatInput.value = '';
        chatInput.style.height = 'auto';
        
        // Remove welcome message if present
        const welcomeMessage = document.querySelector('.welcome-message');
        if (welcomeMessage) {
            welcomeMessage.remove();
        }
        
        // Add user message to the chat
        addMessage('user', message);
        
        // Show loading indicator
        const loadingIndicator = addLoadingIndicator();
        
        try {
            // Send message to API
            const response = await sendMessage(message, currentConversationId);
            
            // Log the complete response for debugging
            console.log('Full API response:', JSON.stringify(response));
            
            // Remove loading indicator
            loadingIndicator.remove();
            
            // First check if the response has a direct image_content field
            if (response.type === 'image' || 
                (response.type === 'text_and_image' && response.image_content)) {
                // Use the provided image_content
                console.log('Using image_content from response:', response.image_content);
                addMessage('assistant', response.text_content || '', response.metadata, response.image_content);
            } 
            // Next, check for markdown image/link patterns in the text
            else if (response.text_content) {
                console.log('Checking text for image URLs:', response.text_content);
                let imageUrl = null;
                let cleanedText = response.text_content;
                
                // Check for [here](URL) format (from screenshot)
                if (response.text_content.includes('[here](')) {
                    const hereMatch = response.text_content.match(/\[here\]\((https?:\/\/[^)]+)\)/i);
                    if (hereMatch && hereMatch[1]) {
                        imageUrl = hereMatch[1];
                        console.log('Found [here] link:', imageUrl);
                        cleanedText = response.text_content.replace(/\[here\]\([^)]+\)/i, '');
                    }
                }
                
                // Check for ![alt](URL) format
                if (!imageUrl && response.text_content.includes('![')) {
                    const markdownMatch = response.text_content.match(/!\[.*?\]\((https?:\/\/[^)]+)\)/i);
                    if (markdownMatch && markdownMatch[1]) {
                        imageUrl = markdownMatch[1];
                        console.log('Found markdown image:', imageUrl);
                        cleanedText = response.text_content.replace(/!\[.*?\]\([^)]+\)/i, '');
                    }
                }
                
                // Check for any URL that looks like an image
                if (!imageUrl) {
                    const urlMatch = response.text_content.match(/(https?:\/\/[^\s"]+\.(?:png|jpg|jpeg|gif))/i);
                    if (urlMatch && urlMatch[1]) {
                        imageUrl = urlMatch[1];
                        console.log('Found raw image URL:', imageUrl);
                        cleanedText = response.text_content.replace(urlMatch[1], '');
                    }
                }
                
                // If we found an image URL, use it
                if (imageUrl) {
                    addMessage('assistant', cleanedText, response.metadata, imageUrl);
                } else {
                    // No image found, just show the text
                    addMessage('assistant', response.text_content, response.metadata);
                }
            } else {
                // Default case: just text
                addMessage('assistant', response.text_content, response.metadata);
            }
            
            // Update conversation history
            updateConversationHistory(message, currentConversationId);
            
        } catch (error) {
            // Remove loading indicator
            loadingIndicator.remove();
            
            // Add appropriate error message
            if (error.message && error.message.includes('timeout')) {
                addMessage('assistant', 'The request timed out after 90 seconds. The request may be too complex or the server might be experiencing high load. Please try again with a simpler prompt.');
            } else if (error.response && error.response.status === 504) {
                addMessage('assistant', 'The request timed out after 90 seconds. The request may be too complex or the server might be experiencing high load. Please try again with a simpler prompt.');
            } else {
                addMessage('assistant', 'Sorry, an error occurred. Please try again.');
            }
            console.error('Error:', error);
        }
    });
    
    // Handle new chat button click
    newChatBtn.addEventListener('click', () => {
        // Check if user is logged in
        if (!currentUser) {
            // Show login overlay if not logged in
            loginOverlay.classList.remove('hidden');
            return;
        }
        
        // Clear chat messages
        clearChatMessages();
        
        // Generate new conversation ID
        currentConversationId = generateConversationId();
        
        // Update active conversation in UI
        updateActiveConversation(currentConversationId);
    });
    
    // Handle conversation history click
    conversationHistory.addEventListener('click', (e) => {
        // Check if user is logged in
        if (!currentUser) {
            // Show login overlay if not logged in
            loginOverlay.classList.remove('hidden');
            return;
        }
        
        if (e.target.classList.contains('conversation-item')) {
            const conversationId = e.target.dataset.id;
            
            // Set current conversation ID
            currentConversationId = conversationId;
            
            // Update active conversation in UI
            updateActiveConversation(currentConversationId);
            
            // Load conversation messages
            loadConversationMessages(currentConversationId);
        } else if (e.target.classList.contains('delete-btn')) {
            // Handle delete button click
            e.stopPropagation();
            const conversationId = e.target.parentElement.dataset.id;
            deleteConversation(conversationId);
        }
    });
    
    // Handle Google login button click
    googleLoginBtn.addEventListener('click', () => {
        window.location.href = '/login/google';
    });
    
    // Handle overlay Google login button click
    if (overlayLoginBtn) {
        overlayLoginBtn.addEventListener('click', () => {
            window.location.href = '/login/google';
        });
    }
    
    // Handle logout button click
    logoutBtn.addEventListener('click', () => {
        // Clean up local storage before redirecting
        localStorage.removeItem('chatUser');
        localStorage.removeItem('chatConversations');
        
        // Redirect to server-side logout
        window.location.href = '/logout';
    });
    
    // Handle clear conversations button click
    clearConversationsBtn.addEventListener('click', () => {
        // Check if user is logged in
        if (!currentUser) {
            // Show login overlay if not logged in
            loginOverlay.classList.remove('hidden');
            return;
        }
        
        showClearModal();
    });
    
    // Handle clear confirm button click
    clearConfirmBtn.addEventListener('click', () => {
        clearAllConversations();
        hideClearModal();
    });
    
    // Handle clear cancel button click
    clearCancelBtn.addEventListener('click', () => {
        hideClearModal();
    });
    
    // Initialize conversation history in UI
    initializeConversationHistory();
    
    // Initialize auth state
    function initializeAuthState(justLoggedOut) {
        // If user just logged out, ensure all login-required elements are reset
        if (justLoggedOut) {
            currentUser = null;
            showLoginForm();
            return;
        }
        
        // Check if user data was passed from the server
        if (typeof serverUser !== 'undefined' && serverUser) {
            currentUser = {
                email: serverUser.email,
                name: serverUser.name,
                picture: serverUser.picture
            };
            showUserInfo();
            loadUserSessions();
            enableChatInput();
            return;
        }
        
        // Fallback to localStorage
        const savedUser = localStorage.getItem('chatUser');
        if (savedUser) {
            currentUser = JSON.parse(savedUser);
            showUserInfo();
            loadUserSessions();
            enableChatInput();
        } else {
            // Not logged in
            currentUser = null;
            showLoginForm();
            disableChatInput();
        }
    }
    
    // Enable chat input
    function enableChatInput() {
        chatInput.disabled = false;
        chatInput.placeholder = "Message ChatGPT...";
    }
    
    // Disable chat input
    function disableChatInput() {
        chatInput.disabled = true;
        chatInput.placeholder = "Please login to chat...";
    }
    
    // Show user info
    function showUserInfo() {
        loginArea.classList.add('hidden');
        userInfo.classList.remove('hidden');
        userEmail.textContent = currentUser.email;
        
        // Hide login overlay
        if (loginOverlay) {
            loginOverlay.classList.add('hidden');
        }
        
        // If user has a profile picture (from Google)
        if (currentUser.picture && !document.querySelector('.profile-pic')) {
            const profilePic = document.createElement('img');
            profilePic.src = currentUser.picture;
            profilePic.alt = 'Profile';
            profilePic.classList.add('profile-pic');
            userInfo.insertBefore(profilePic, userEmail);
        }
    }
    
    // Show login form
    function showLoginForm() {
        // Reset user UI elements
        userInfo.classList.add('hidden');
        loginArea.classList.remove('hidden');
        
        // Show login overlay
        if (loginOverlay) {
            loginOverlay.classList.remove('hidden');
        }
        
        // Clear conversation history display
        conversations = [];
        updateConversationHistoryUI();
        
        // Reset chat display
        clearChatMessages(true);
        
        // Disable input
        disableChatInput();
        
        // Remove any active conversation highlighting
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
    }
    
    // Load user sessions from server
    async function loadUserSessions() {
        if (!currentUser) return;
        
        try {
            const response = await fetch('/api/v1/sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email_id: currentUser.email
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('User sessions:', data);
            
            if (data.sessions && data.sessions.length > 0) {
                // Convert server sessions to local format
                conversations = data.sessions.map(session => ({
                    id: session.session_id,
                    title: session.last_message || `Conversation ${new Date(session.created_at * 1000).toLocaleString()}`,
                    lastUpdated: session.updated_at * 1000,
                    email: session.email_id,
                    messages: []
                }));
                
                // Save to local storage
                saveConversations();
                
                // Update UI
                updateConversationHistoryUI();
                
                // Set current conversation to the most recent one
                if (conversations.length > 0) {
                    currentConversationId = conversations[0].id;
                    updateActiveConversation(currentConversationId);
                    loadConversationHistory(currentConversationId);
                }
                
                // Hide placeholder
                historyPlaceholder.classList.add('hidden');
            } else {
                // No sessions found
                historyPlaceholder.textContent = 'No conversation history found. Start a new chat!';
                historyPlaceholder.classList.remove('hidden');
                conversations = [];
                saveConversations();
                updateConversationHistoryUI();
            }
            
        } catch (error) {
            console.error('Error loading user sessions:', error);
            alert('Failed to load your conversation history. Please try again later.');
        }
    }
    
    // Load conversation history from server
    async function loadConversationHistory(sessionId) {
        if (!currentUser) return;
        
        try {
            const response = await fetch('/api/v1/conversation-history', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    email_id: currentUser.email
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Conversation history:', data);
            
            if (data.messages && data.messages.length > 0) {
                // Clear chat messages
                clearChatMessages(false); // Don't show welcome message
                
                // Add messages to chat
                data.messages.forEach(message => {
                    addMessage(
                        message.role, 
                        message.content, 
                        null, // No metadata in the history
                        null  // No image URL in the history
                    );
                });
            } else {
                // No messages found
                clearChatMessages(); // Show welcome message
            }
            
        } catch (error) {
            console.error('Error loading conversation history:', error);
            alert('Failed to load conversation history. Please try again later.');
            clearChatMessages();
        }
    }
    
    // Delete a conversation
    async function deleteConversation(conversationId) {
        if (!confirm('Are you sure you want to delete this conversation?')) return;
        
        try {
            if (currentUser) {
                // Delete from server
                const response = await fetch('/api/v1/clear-conversation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        conversation_id: conversationId,
                        email_id: currentUser.email
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                console.log('Conversation deleted from server');
            }
            
            // Remove from local conversations
            conversations = conversations.filter(conv => conv.id !== conversationId);
            saveConversations();
            
            // Update UI
            updateConversationHistoryUI();
            
            // If the deleted conversation was the current one, create a new chat
            if (conversationId === currentConversationId) {
                newChatBtn.click();
            }
            
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('Failed to delete conversation. Please try again later.');
        }
    }
    
    // Clear all conversations
    async function clearAllConversations() {
        try {
            if (currentUser) {
                // Clear from server
                const response = await fetch('/api/v1/clear-conversation', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email_id: currentUser.email
                    })
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                
                console.log('All conversations cleared from server');
            }
            
            // Clear local conversations
            conversations = [];
            saveConversations();
            
            // Update UI
            updateConversationHistoryUI();
            
            // Create a new chat
            newChatBtn.click();
            
        } catch (error) {
            console.error('Error clearing conversations:', error);
            alert('Failed to clear conversations. Please try again later.');
        }
    }
    
    // Show clear modal
    function showClearModal() {
        clearModal.classList.add('show');
    }
    
    // Hide clear modal
    function hideClearModal() {
        clearModal.classList.remove('show');
    }
    
    // Function to send message to API
    async function sendMessage(message, conversationId) {
        const requestBody = {
            message: message,
            conversation_id: conversationId
        };
        
        // Add email if user is logged in
        if (currentUser) {
            requestBody.email_id = currentUser.email;
        }
        
        const response = await fetch('/api/v1/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const error = new Error(`HTTP error! status: ${response.status}`);
            error.response = response;
            error.responseData = errorData;
            throw error;
        }
        
        return await response.json();
    }
    
    // Function to add a message to the chat
    function addMessage(sender, content, metadata = null, imageUrl = null) {
        console.log('Adding message with content:', content);
        console.log('Image URL:', imageUrl);
        
        // Check if this is the specific scenario from the screenshot
        if (content && content.includes('[here](') && !imageUrl) {
            // Extract the URL from [here](URL) format
            const hereMatch = content.match(/\[here\]\((https?:\/\/[^)]+)\)/i);
            if (hereMatch && hereMatch[1]) {
                imageUrl = hereMatch[1];
                console.log('Extracted image URL from [here] link:', imageUrl);
                
                // Remove the [here](URL) part from the content
                content = content.replace(/\[here\]\([^)]+\)/i, '');
            }
        }
        
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message');
        messageDiv.classList.add(sender === 'user' ? 'user-message' : 'assistant-message');
        
        // Add message content
        const messageContent = document.createElement('div');
        messageContent.classList.add('message-content');
        
        // If we have an imageUrl, try to extract it directly from the content first for better link removal
        if (imageUrl && content && content.includes(imageUrl)) {
            console.log('Image URL found directly in content, removing it');
            content = content.replace(imageUrl, '');
        }
        
        // Check for [here](url) pattern to display correctly and to avoid displaying the link text
        if (content) {
            // First check for [here](url) pattern
            content = content.replace(/\[here\]\((https?:\/\/[^)]+)\)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">here</a>');
            
            // Then convert other markdown links to HTML but not the image links we're going to display
            content = content.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
                    .replace(/!\[.*?\]\(.*?\)/g, ''); // Remove markdown image syntax
        }
        
        messageContent.innerHTML = content || ''; // Use innerHTML to render the HTML links
        messageDiv.appendChild(messageContent);
        
        // Add image if present
        if (imageUrl) {
            console.log('Adding image with URL:', imageUrl);
            const imageContainer = document.createElement('div');
            imageContainer.classList.add('image-container');
            
            const imageElement = document.createElement('img');
            imageElement.src = imageUrl;
            imageElement.alt = 'Assistant generated image';
            imageElement.style.maxWidth = '100%';
            imageElement.style.marginTop = '10px';
            imageElement.style.borderRadius = '6px';
            
            // Add loading state
            imageElement.style.opacity = '0.6';
            const loadingText = document.createElement('div');
            loadingText.textContent = 'Loading image...';
            loadingText.style.textAlign = 'center';
            loadingText.style.marginTop = '5px';
            loadingText.style.fontSize = '12px';
            loadingText.style.color = '#8e8ea0';
            
            imageContainer.appendChild(imageElement);
            imageContainer.appendChild(loadingText);
            messageDiv.appendChild(imageContainer);
            
            // Remove loading state once image is loaded
            imageElement.onload = () => {
                imageElement.style.opacity = '1';
                loadingText.remove();
            };
            
            // Handle image error
            imageElement.onerror = () => {
                loadingText.textContent = 'Failed to load image. Click to view: ';
                
                // Add a direct link to the image
                const linkElement = document.createElement('a');
                linkElement.href = imageUrl;
                linkElement.target = '_blank';
                linkElement.rel = 'noopener noreferrer';
                linkElement.textContent = 'Open image in new tab';
                linkElement.style.color = '#7c84f8';
                linkElement.style.textDecoration = 'underline';
                
                loadingText.appendChild(linkElement);
                imageElement.style.display = 'none';
            };
        }
        
        // Add metadata if present
        if (metadata && metadata.cost) {
            const metadataDiv = document.createElement('div');
            metadataDiv.classList.add('message-metadata');
            
            const costInfo = metadata.cost;
            const totalCost = costInfo.total_cost_usd;
            const totalTokens = costInfo.total_tokens;
            
            metadataDiv.textContent = `Tokens: ${totalTokens} | Cost: $${totalCost.toFixed(6)}`;
            messageDiv.appendChild(metadataDiv);
        }
        
        chatMessages.appendChild(messageDiv);
        
        // Scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    // Function to add loading indicator
    function addLoadingIndicator() {
        const loadingDiv = document.createElement('div');
        loadingDiv.classList.add('chat-message', 'assistant-message', 'loading-message');
        
        const loadingContent = document.createElement('div');
        loadingContent.classList.add('message-content');
        loadingContent.textContent = 'Thinking...';
        loadingDiv.appendChild(loadingContent);
        
        chatMessages.appendChild(loadingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return loadingDiv;
    }
    
    // Function to clear chat messages
    function clearChatMessages(showWelcome = true) {
        if (showWelcome) {
            chatMessages.innerHTML = `
                <div class="welcome-message">
                    <h1>ChatGPT Clone</h1>
                    <p>How can I help you today?</p>
                </div>
            `;
        } else {
            chatMessages.innerHTML = '';
        }
    }
    
    // Function to generate a conversation ID
    function generateConversationId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    }
    
    // Function to update conversation history
    function updateConversationHistory(message, conversationId) {
        // Check if conversation already exists
        const existingConversation = conversations.find(conv => conv.id === conversationId);
        
        if (existingConversation) {
            // Update existing conversation
            existingConversation.title = message.substring(0, 30) + (message.length > 30 ? '...' : '');
            existingConversation.lastUpdated = Date.now();
            if (currentUser) {
                existingConversation.email = currentUser.email;
            }
        } else {
            // Add new conversation
            const newConversation = {
                id: conversationId,
                title: message.substring(0, 30) + (message.length > 30 ? '...' : ''),
                lastUpdated: Date.now(),
                email: currentUser ? currentUser.email : null,
                messages: []
            };
            
            conversations.unshift(newConversation);
        }
        
        // Save conversations to local storage
        saveConversations();
        
        // Update UI
        updateConversationHistoryUI();
    }
    
    // Function to initialize conversation history
    function initializeConversationHistory() {
        updateConversationHistoryUI();
    }
    
    // Function to update conversation history UI
    function updateConversationHistoryUI() {
        // Clear previous history except placeholder
        const elements = conversationHistory.querySelectorAll('.conversation-item');
        elements.forEach(el => el.remove());
        
        // Show/hide placeholder based on conversations
        if (conversations.length === 0) {
            historyPlaceholder.classList.remove('hidden');
        } else {
            historyPlaceholder.classList.add('hidden');
        }
        
        // Filter conversations by current user if logged in
        let filteredConversations = conversations;
        if (currentUser) {
            filteredConversations = conversations.filter(
                conv => !conv.email || conv.email === currentUser.email
            );
        }
        
        // Add conversations to UI
        filteredConversations.forEach(conversation => {
            const conversationItem = document.createElement('div');
            conversationItem.classList.add('conversation-item');
            conversationItem.dataset.id = conversation.id;
            conversationItem.textContent = conversation.title;
            
            // Add delete button
            const deleteBtn = document.createElement('button');
            deleteBtn.classList.add('delete-btn');
            deleteBtn.innerHTML = '&times;';
            deleteBtn.title = 'Delete conversation';
            conversationItem.appendChild(deleteBtn);
            
            if (conversation.id === currentConversationId) {
                conversationItem.classList.add('active');
            }
            
            conversationHistory.insertBefore(conversationItem, historyPlaceholder);
        });
    }
    
    // Function to update active conversation
    function updateActiveConversation(conversationId) {
        // Remove active class from all conversation items
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Add active class to current conversation item
        const currentItem = document.querySelector(`.conversation-item[data-id="${conversationId}"]`);
        if (currentItem) {
            currentItem.classList.add('active');
        }
    }
    
    // Function to load conversation messages
    function loadConversationMessages(conversationId) {
        // Clear chat messages
        clearChatMessages();
        
        // Find conversation
        const conversation = conversations.find(conv => conv.id === conversationId);
        
        if (conversation && conversation.messages && conversation.messages.length > 0) {
            // Remove welcome message
            const welcomeMessage = document.querySelector('.welcome-message');
            if (welcomeMessage) {
                welcomeMessage.remove();
            }
            
            // Add messages to chat
            conversation.messages.forEach(message => {
                addMessage(message.sender, message.content, message.metadata, message.imageUrl);
            });
        }
        
        // If user is logged in, try to load from server
        if (currentUser && currentUser.email) {
            loadConversationHistory(conversationId);
        }
    }
    
    // Function to load conversations from local storage
    function loadConversations() {
        const savedConversations = localStorage.getItem('chatConversations');
        return savedConversations ? JSON.parse(savedConversations) : [];
    }
    
    // Function to save conversations to local storage
    function saveConversations() {
        localStorage.setItem('chatConversations', JSON.stringify(conversations));
    }
}); 