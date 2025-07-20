export const copyHashLink = (hashLink, showMessage) => {
    const fullUrl = `https://sowfeehealth.com/survey/link/${hashLink}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
        showMessage('Survey template link copied to clipboard!', 'success');
    }).catch(() => {
        showMessage('Failed to copy link to clipboard', 'error');
    });
};

export const showMessage = (setMessage) => (msg, type = 'success') => {
    setMessage({ text: msg, type });
    setTimeout(() => setMessage({ text: '', type: '' }), 2500);
};