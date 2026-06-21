const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('jarvis', {
  min: () => ipcRenderer.invoke('win:min'),
  max: () => ipcRenderer.invoke('win:max'),
  close: () => ipcRenderer.invoke('win:close'),
  backendUrl: () => ipcRenderer.invoke('backend:url')
});
